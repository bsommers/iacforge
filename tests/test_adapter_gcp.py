import copy
import importlib.util

import pytest

from iacforge.adapters.gcp import EXAMPLES
from iacforge.errors import SpecError
from iacforge.render import bind, render_terraform
from iacforge.spec import parse_spec


def doc():
    return copy.deepcopy(EXAMPLES[0])


def render(d):
    return render_terraform(bind(parse_spec(d), "opentofu"))


def res(d, name):
    return next(r for r in d["spec"]["resources"] if r["name"] == name)


def test_structure():
    out = render(doc())
    assert out["provider"]["google"] == {"project": "my-project", "region": "us-central1", "zone": "us-central1-a"}
    web = out["resource"]["google_compute_instance"]["web"]
    assert web["network_interface"][0]["subnetwork"] == "${google_compute_subnetwork.subnet_a.self_link}"
    assert web["network_interface"][0]["access_config"] == [{}]
    assert web["service_account"]["email"] == "${google_service_account.sa.email}"
    assert web["scheduling"]["provisioning_model"] == "SPOT"
    assert web["labels"] == {"managed-by": "iacforge"}
    assert web["boot_disk"]["initialize_params"]["image"] == "debian-cloud/debian-12"
    assert out["resource"]["google_compute_network"]["vpc"]["auto_create_subnetworks"] is False
    b = out["resource"]["google_storage_bucket"]["data_bucket_example_1"]
    assert b["uniform_bucket_level_access"] is True and b["versioning"] == {"enabled": True}
    assert "web__external_ip" in out["output"] and "vpc__self_link" in out["output"]
    assert out["output"]["data_bucket_example_1__url"]


def test_deps():
    out = render(doc())
    assert out["resource"]["google_compute_instance"]["web"]["depends_on"] == sorted(
        ["google_compute_subnetwork.subnet_a", "google_service_account.sa"])
    assert out["resource"]["google_compute_firewall"]["allow_ssh"]["depends_on"] == ["google_compute_network.vpc"]


def test_no_public_ip_no_external_output():
    d = doc()
    res(d, "web")["properties"]["publicIp"] = False
    out = render(d)
    assert "web__external_ip" not in out["output"]
    assert "access_config" not in out["resource"]["google_compute_instance"]["web"]["network_interface"][0]


@pytest.mark.parametrize("mutate", [
    lambda d: d["spec"]["providerConfig"].pop("project"),
    lambda d: res(d, "subnet-a")["properties"].update(cidr="10.0.0.0/33"),
    lambda d: res(d, "subnet-a")["properties"].update(cidr="nope"),
    lambda d: res(d, "web")["properties"].update(bogus=1),
    lambda d: d["spec"]["providerConfig"].update(credentials="x"),
    lambda d: res(d, "web")["properties"].update(network="vpc"),
    lambda d: res(d, "web")["properties"].update(subnet="missing"),
    lambda d: res(d, "web")["properties"].update(subnet="vpc"),
    lambda d: res(d, "web")["properties"].update(preemptible=True),
    lambda d: res(d, "allow-ssh")["properties"].pop("sourceRanges"),
    lambda d: res(d, "sa")["properties"].update(accountId="X"),
    lambda d: res(d, "data-bucket-example-1")["properties"].update(bucketName="Bad_Name"),
])
def test_invalid(mutate):
    d = doc()
    mutate(d)
    with pytest.raises(SpecError):
        bind(parse_spec(d), "opentofu")


def test_vm_requires_network():
    d = doc()
    del res(d, "web")["properties"]["subnet"]
    with pytest.raises(SpecError):
        bind(parse_spec(d), "opentofu")


def test_firewall_egress_default_range():
    d = doc()
    res(d, "allow-ssh")["properties"].update(direction="EGRESS")
    res(d, "allow-ssh")["properties"].pop("sourceRanges")
    fw = render(d)["resource"]["google_compute_firewall"]["allow_ssh"]
    assert fw["destination_ranges"] == ["0.0.0.0/0"] and "source_ranges" not in fw


@pytest.mark.skipif(not (importlib.util.find_spec("pulumi") and importlib.util.find_spec("pulumi_gcp")),
                    reason="pulumi_gcp not installed")
def test_pulumi_mocks():
    import pulumi

    class M(pulumi.runtime.Mocks):
        def new_resource(self, args):
            return [args.name + "_id", args.inputs]

        def call(self, args):
            return {}

    pulumi.runtime.set_mocks(M(), project="p", stack="s", preview=False)
    from iacforge.render import run_pulumi_program

    run_pulumi_program(bind(parse_spec(doc()), "pulumi"))
