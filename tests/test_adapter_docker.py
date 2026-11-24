import copy
import json
import shutil
import subprocess

import pytest

from iacforge.adapters.docker import ADAPTER, EXAMPLES
from iacforge.errors import SpecError
from iacforge.render import bind, nest_outputs, render_terraform
from iacforge.spec import parse_spec


def stack(resources, config=None, engine="opentofu"):
    spec = {"provider": "docker", "engine": engine, "resources": resources}
    if config is not None:
        spec["providerConfig"] = config
    return {"apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "t"}, "spec": spec}


def tf(resources, config=None):
    return render_terraform(bind(parse_spec(stack(resources, config))))


def res(rname, type_, /, **props):
    return {"name": rname, "type": type_, "properties": props}


def test_example_structure():
    doc = tf(EXAMPLES[0]["spec"]["resources"])
    assert doc["terraform"]["required_providers"]["docker"] == {
        "source": "kreuzwerker/docker", "version": "~> 3.0"}
    assert "provider" not in doc or doc["provider"] == {"docker": {}}
    r = doc["resource"]
    assert set(r) == {"docker_container", "docker_image", "docker_network", "docker_volume"}
    assert r["docker_network"]["net"] == {
        "name": "net", "driver": "bridge", "internal": False,
        "ipam_config": [{"subnet": "172.30.0.0/24"}],
        "labels": [{"label": "env", "value": "dev"}]}
    assert r["docker_volume"]["data"]["name"] == "data"
    assert r["docker_image"]["base"] == {"name": "nginx:1.27-alpine", "keep_locally": True}
    web = r["docker_container"]["web"]
    assert web["image"] == "${docker_image.base.image_id}"
    assert web["env"] == ["A=1", "B=2"]
    assert web["ports"] == [{"internal": 80, "protocol": "tcp", "external": 8080}]
    assert web["volumes"] == [{"container_path": "/data", "read_only": False,
                               "volume_name": "${docker_volume.data.name}"}]
    assert web["networks_advanced"] == [{"name": "${docker_network.net.name}"}]
    assert web["restart"] == "unless-stopped" and web["memory"] == 128
    assert web["labels"] == [{"label": "app", "value": "web"}]
    assert sorted(web["depends_on"]) == ["docker_image.base", "docker_network.net", "docker_volume.data"]
    job = r["docker_container"]["job"]
    assert job["image"] == "alpine:3.20" and job["command"] == ["sleep", "3600"]
    assert job["volumes"] == [{"container_path": "/host", "read_only": True, "host_path": "/tmp"}]
    assert "depends_on" not in job


def test_outputs():
    doc = tf(EXAMPLES[0]["spec"]["resources"])
    out = doc["output"]
    assert out["web__id"]["value"] == "${docker_container.web.id}"
    assert "network_data" in out["web__ip_address"]["value"]
    assert "web__ip_addresses" in out and "net__id" in out and "data__name" in out
    assert "base__image_id" in out
    assert nest_outputs({k: 1 for k in out})["web"].keys() >= {"id", "name", "ip_address"}


def test_provider_config():
    doc = tf([res("n", "network")], {
        "host": "npipe:////./pipe/docker_engine",
        "registryAuth": [{"address": "ghcr.io", "username": "u", "password": "p"}]})
    assert doc["provider"]["docker"] == {
        "host": "npipe:////./pipe/docker_engine",
        "registry_auth": [{"address": "ghcr.io", "username": "u", "password": "p"}]}
    doc = tf([res("n", "network")], {"host": "unix:///run/user/1000/podman/podman.sock"})
    assert doc["provider"]["docker"]["host"].endswith("podman.sock")


def test_references():
    p = ADAPTER.resource_models["container"].model_validate(
        {"imageFrom": "i", "networks": ["n1", "n2"], "volumes": [{"volume": "v", "containerPath": "/v"},
                                                                  {"hostPath": "/h", "containerPath": "/h"}]})
    assert ADAPTER.references(type("R", (), {"type": "container"})(), p) == ["i", "n1", "n2", "v"]
    b = bind(parse_spec(stack([
        res("c", "container", image="alpine", networks=["n"]), res("n", "network")])))
    assert [r.name for r in b.order] == ["n", "c"]
    assert b.order[1].depends_on == ["n"]


def test_deterministic_key_order():
    a = tf([res("c", "container", image="x", env={"B": "1", "A": "2"}, labels={"z": "1", "a": "2"})])
    b = tf([res("c", "container", image="x", env={"A": "2", "B": "1"}, labels={"a": "2", "z": "1"})])
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["resource"]["docker_container"]["c"]["labels"][0]["label"] == "a"


@pytest.mark.parametrize("resources, needle", [
    ([res("c", "container")], "image"),
    ([res("c", "container", image="a", imageFrom="b")], "exactly one"),
    ([res("c", "container", image="a", ports=[{"internal": 0}])], "internal"),
    ([res("c", "container", image="a", ports=[{"internal": 80, "protocol": "icmp"}])], "protocol"),
    ([res("c", "container", image="a", restart="sometimes")], "restart"),
    ([res("c", "container", image="a", volumes=[{"containerPath": "/x"}])], "exactly one"),
    ([res("c", "container", image="a", volumes=[{"volume": "v", "hostPath": "/h", "containerPath": "/x"}])],
     "exactly one"),
    ([res("c", "container", image="a", memoryMb=1)], "memory"),
    ([res("n", "network", subnet="bogus")], "subnet"),
    ([res("i", "image")], "name"),
    ([res("v", "volume", bogus=1)], "bogus"),
])
def test_property_validation_negatives(resources, needle):
    with pytest.raises(SpecError) as ei:
        bind(parse_spec(stack(resources)))
    assert needle.lower() in json.dumps(ei.value.details, default=str).lower()


def test_unknown_config_key_rejected():
    with pytest.raises(SpecError):
        bind(parse_spec(stack([res("n", "network")], {"hots": "x"})))


def test_unknown_reference_rejected():
    with pytest.raises(SpecError) as ei:
        bind(parse_spec(stack([res("c", "container", image="a", networks=["ghost"])])))
    assert "ghost" in json.dumps(ei.value.details)


def test_wrong_type_reference_rejected():
    with pytest.raises(SpecError) as ei:
        bind(parse_spec(stack([res("v", "volume"), res("c", "container", image="a", networks=["v"])])))
    assert "expected a network" in json.dumps(ei.value.details)
    with pytest.raises(SpecError):
        bind(parse_spec(stack([res("n", "network"), res("c", "container", imageFrom="n")])))


def test_example_not_mutated_by_render():
    before = copy.deepcopy(EXAMPLES)
    tf(EXAMPLES[0]["spec"]["resources"])
    assert before == EXAMPLES


# ---- pulumi (mocks; needs pulumi + pulumi_docker importable) ----
def test_pulumi_program_with_mocks():
    pulumi = pytest.importorskip("pulumi")
    pytest.importorskip("pulumi_docker")
    created = []

    class Mocks(pulumi.runtime.Mocks):
        def new_resource(self, args):
            created.append((args.typ, args.name, dict(args.inputs)))
            return [args.name + "_id", {**args.inputs, "imageId": "sha256:abc",
                                        "networkDatas": [{"ipAddress": "10.0.0.2"}]}]

        def call(self, args):
            return {}

    pulumi.runtime.set_mocks(Mocks(), project="t", stack="t", preview=False)
    from iacforge.render import run_pulumi_program

    exported = {}

    @pulumi.runtime.test
    def program():
        orig = pulumi.export
        pulumi.export = lambda k, v: exported.__setitem__(k, v)
        try:
            run_pulumi_program(bind(parse_spec(stack(EXAMPLES[0]["spec"]["resources"], engine="pulumi"))))
        finally:
            pulumi.export = orig
        return pulumi.Output.all(*exported.values())

    program()
    types = [t for t, _, _ in created]
    assert types.count("docker:index/container:Container") == 2
    assert "docker:index/network:Network" in types
    assert "docker:index/volume:Volume" in types
    assert "docker:index/remoteImage:RemoteImage" in types
    assert "web__ip_address" in exported and "net__id" in exported


# ---- live ----
def _docker_ok():
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.mark.docker
@pytest.mark.tofu
def test_live_apply_alpine(tmp_path):
    if not _docker_ok():
        pytest.skip("docker daemon not available")
    engines = pytest.importorskip("iacforge.engines.terraform")
    from .conftest import tf_binary
    if not tf_binary():
        pytest.skip("tofu/terraform not installed")
    b = bind(parse_spec(stack([
        res("net", "network"),
        res("img", "image", name="alpine:3.20", keepLocally=True),
        res("box", "container", imageFrom="img", command=["sleep", "60"], networks=["net"],
            name="iacforge-live-box"),
    ])))
    eng = engines.TerraformEngine("opentofu")
    try:
        out = eng.apply(b, tmp_path)
        assert out["outputs"]["box"]["name"] == "iacforge-live-box"
        assert out["outputs"]["box"]["ip_address"]
    finally:
        eng.destroy(b, tmp_path)
