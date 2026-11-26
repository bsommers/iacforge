"""spec.backend (ADR 0005): model, binding, Terraform block, -reconfigure, Pulumi URL/passphrase."""
import json

import pytest

from iacforge.engines.base import ProcResult
from iacforge.engines.pulumi import PulumiEngine, backend_url
from iacforge.engines.terraform import TerraformEngine
from iacforge.errors import SpecError, UnsupportedError
from iacforge.render import bind, render_terraform
from iacforge.spec import Backend, parse_spec

GCS = {"type": "gcs", "bucket": "my-state-bkt"}


def spec(backend=None, engine="opentofu"):
    body = {"provider": "gcp", "engine": engine,
            "providerConfig": {"project": "proj-1", "region": "us-central1"},
            "resources": [{"name": "b1", "type": "bucket",
                           "properties": {"bucketName": "iacforge-b1-test"}}]}
    if backend is not None:
        body["backend"] = backend
    return {"apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "s1"}, "spec": body}


def local_spec(backend=None):
    d = {"apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "s1"},
         "spec": {"provider": "local", "resources": [
             {"name": "f", "type": "file", "properties": {"path": "a.txt", "content": "x"}}]}}
    if backend is not None:
        d["spec"]["backend"] = backend
    return d


# ------------------------------------------------------------ model
def test_default_backend_is_local():
    b = parse_spec(local_spec()).spec.backend
    assert b.type == "local" and b.bucket is None and b.prefix == "iacforge"


def test_gcs_requires_bucket():
    with pytest.raises(ValueError, match="requires 'bucket'"):
        Backend(type="gcs")


def test_local_forbids_bucket():
    with pytest.raises(ValueError, match="only valid for remote"):
        Backend(type="local", bucket="abc")


@pytest.mark.parametrize("prefix", ["", "/x", "x/", "a b", "a//b", "a$"])
def test_bad_prefix(prefix):
    with pytest.raises(ValueError):
        Backend(type="gcs", bucket="abc", prefix=prefix)


@pytest.mark.parametrize("prefix", ["iacforge", "a/b", "team.x-1_y"])
def test_good_prefix(prefix):
    assert Backend(type="gcs", bucket="abc", prefix=prefix).prefix == prefix


def test_unknown_field_forbidden():
    with pytest.raises(ValueError):
        Backend(type="gcs", bucket="abc", credentials="x")


def test_state_key():
    assert Backend(**GCS).state_key("s1", "pulumi") == "iacforge/s1/pulumi"
    assert Backend(**GCS, prefix="a/b").state_key("s1", "opentofu") == "a/b/s1/opentofu"


# ------------------------------------------------------------ bind
def test_bind_rejects_gcs_for_docker():
    d = local_spec(GCS)
    d["spec"]["provider"] = "docker"
    d["spec"]["resources"] = []
    with pytest.raises(UnsupportedError, match="backend"):
        bind(parse_spec(d))


def test_bind_rejects_gcs_for_local_provider():
    with pytest.raises(UnsupportedError):
        bind(parse_spec(local_spec(GCS)))


def test_bind_accepts_gcs_for_gcp_and_state_key_follows_engine():
    b = bind(parse_spec(spec(GCS)))
    assert b.state_key == "iacforge/s1/opentofu"
    assert bind(parse_spec(spec(GCS)), "terraform").state_key == "iacforge/s1/terraform"


# ------------------------------------------------------------ terraform render
def test_tf_backend_block():
    doc = render_terraform(bind(parse_spec(spec({**GCS, "prefix": "pfx"}))))
    assert doc["terraform"]["backend"] == {"gcs": {"bucket": "my-state-bkt",
                                                   "prefix": "pfx/s1/opentofu"}}


def test_tf_no_backend_block_for_local():
    assert "backend" not in render_terraform(bind(parse_spec(local_spec())))["terraform"]
    assert "backend" not in render_terraform(bind(parse_spec(spec())))["terraform"]


# ------------------------------------------------------------ terraform init
class Fake:
    def __init__(self):
        self.calls = []

    def __call__(self, args, cwd, env=None, timeout=None):
        self.calls.append(list(args))
        return ProcResult(0, "", "")


def tf(f):
    return TerraformEngine(runner=f, which=lambda n: "/bin/tofu")


def test_init_reconfigure_for_remote(tmp_path):
    f = Fake()
    eng = tf(f)
    eng.render(bind(parse_spec(spec(GCS))), tmp_path)
    eng._init("/bin/tofu", tmp_path, True)
    assert "-reconfigure" in f.calls[0] and "-migrate-state" not in f.calls[0]


def test_init_no_reconfigure_for_local(tmp_path):
    f = Fake()
    eng = tf(f)
    eng.render(bind(parse_spec(local_spec())), tmp_path)
    eng._init("/bin/tofu", tmp_path)
    assert "-reconfigure" not in f.calls[0]


def test_prepare_passes_remote_flag(tmp_path):
    f = Fake()
    tf(f)._prepare(bind(parse_spec(spec(GCS))), tmp_path)
    assert "-reconfigure" in f.calls[0]


def test_init_stamp_skip_kept_for_remote(tmp_path):
    f = Fake()
    eng = tf(f)
    eng.render(bind(parse_spec(spec(GCS))), tmp_path)
    (tmp_path / ".terraform.lock.hcl").write_text("")
    eng._init("/bin/tofu", tmp_path, True)
    eng._init("/bin/tofu", tmp_path, True)
    assert len(f.calls) == 1


# ------------------------------------------------------------ pulumi
def pbound(backend=GCS):
    return bind(parse_spec(spec(backend, engine="pulumi")))


def test_pulumi_urls(tmp_path):
    assert backend_url(pbound(), tmp_path) == "gs://my-state-bkt/iacforge/s1/pulumi"
    lb = bind(parse_spec(local_spec()), "pulumi")
    assert backend_url(lb, tmp_path) == f"file://{tmp_path.as_posix()}/state"


def test_pulumi_env_remote(tmp_path, monkeypatch):
    monkeypatch.setenv("PULUMI_CONFIG_PASSPHRASE", "pw")
    env = PulumiEngine()._env(tmp_path, pbound())
    assert env["PULUMI_BACKEND_URL"] == "gs://my-state-bkt/iacforge/s1/pulumi"
    assert env["PULUMI_CONFIG_PASSPHRASE"] == "pw"


@pytest.mark.parametrize("val", [None, ""])
def test_pulumi_remote_requires_passphrase(tmp_path, monkeypatch, val):
    if val is None:
        monkeypatch.delenv("PULUMI_CONFIG_PASSPHRASE", raising=False)
    else:
        monkeypatch.setenv("PULUMI_CONFIG_PASSPHRASE", val)
    eng = PulumiEngine(which=lambda n: "/bin/pulumi")
    eng._open_stack = lambda b, wd: pytest.fail("must not open stack")
    with pytest.raises(SpecError, match="PULUMI_CONFIG_PASSPHRASE"):
        eng.plan(pbound(), tmp_path / "wd")
    assert not (tmp_path / "wd" / "state").exists()


def test_pulumi_local_needs_no_passphrase(tmp_path, monkeypatch):
    monkeypatch.delenv("PULUMI_CONFIG_PASSPHRASE", raising=False)
    eng = PulumiEngine(which=lambda n: "/bin/pulumi")
    sentinel = object()
    eng._open_stack = lambda b, wd: sentinel
    with eng._stack(bind(parse_spec(local_spec()), "pulumi"), tmp_path / "wd") as st:
        assert st is sentinel


def test_pulumi_yaml_remote_and_local(tmp_path):
    PulumiEngine().render(pbound(), tmp_path / "r")
    assert "url: gs://my-state-bkt/iacforge/s1/pulumi" in (tmp_path / "r" / "Pulumi.yaml").read_text()
    PulumiEngine().render(bind(parse_spec(local_spec()), "pulumi"), tmp_path / "l")
    assert "url: file://./state" in (tmp_path / "l" / "Pulumi.yaml").read_text()
    st = json.loads((tmp_path / "r" / "stack.json").read_text())
    assert parse_spec(st).spec.backend.bucket == "my-state-bkt"
