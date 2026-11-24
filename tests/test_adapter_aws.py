import copy
import importlib.util

import pytest

from iacforge.adapters.aws import EXAMPLES
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
    assert out["provider"]["aws"] == {"region": "us-east-1", "default_tags": {"tags": {"managed-by": "iacforge"}}}
    web = out["resource"]["aws_instance"]["web"]
    assert web["ami"] == "${data.aws_ami.web_ami.id}"
    assert out["data"]["aws_ami"]["web_ami"]["owners"] == ["099720109477"]
    assert web["subnet_id"] == "${aws_subnet.pub_a.id}"
    assert web["vpc_security_group_ids"] == ["${aws_security_group.web_sg.id}"]
    assert web["associate_public_ip_address"] is True
    sg = out["resource"]["aws_security_group"]["web_sg"]
    assert sg["egress"][0]["protocol"] == "-1" and sg["ingress"][1]["to_port"] == 80
    ver = out["resource"]["aws_s3_bucket_versioning"]["assets_example_bucket_1_versioning"]
    assert ver["bucket"] == "${aws_s3_bucket.assets_example_bucket_1.id}"
    assert "web__public_ip" in out["output"]


def test_deps():
    out = render(doc())
    assert out["resource"]["aws_instance"]["web"]["depends_on"] == ["aws_security_group.web_sg", "aws_subnet.pub_a"]


def test_explicit_ami_no_data():
    d = doc()
    p = res(d, "web")["properties"]
    del p["amiLookup"]
    p["ami"] = "ami-123"
    out = render(d)
    assert "data" not in out and out["resource"]["aws_instance"]["web"]["ami"] == "ami-123"


def test_no_versioning_no_extra():
    d = doc()
    res(d, "assets-example-bucket-1")["properties"]["versioning"] = False
    assert "aws_s3_bucket_versioning" not in render(d)["resource"]


@pytest.mark.parametrize("mutate", [
    lambda d: res(d, "vpc")["properties"].update(cidr="10.0.0.0/99"),
    lambda d: res(d, "vpc")["properties"].pop("cidr"),
    lambda d: res(d, "web")["properties"].update(ami="ami-1"),
    lambda d: res(d, "web")["properties"].pop("amiLookup"),
    lambda d: res(d, "web")["properties"].update(bogus=1),
    lambda d: res(d, "web")["properties"].update(securityGroups=["vpc"]),
    lambda d: res(d, "web")["properties"].update(subnet="nope"),
    lambda d: d["spec"]["providerConfig"].update(accessKey="x"),
    lambda d: res(d, "web-sg")["properties"]["ingress"][0].update(toPort=1),
])
def test_invalid(mutate):
    d = doc()
    mutate(d)
    with pytest.raises(SpecError):
        bind(parse_spec(d), "opentofu")


@pytest.mark.skipif(not (importlib.util.find_spec("pulumi") and importlib.util.find_spec("pulumi_aws")),
                    reason="pulumi_aws not installed")
def test_pulumi_mocks():
    import pulumi

    class M(pulumi.runtime.Mocks):
        def new_resource(self, args):
            return [args.name + "_id", args.inputs]

        def call(self, args):
            return {"id": "ami-1"}

    pulumi.runtime.set_mocks(M(), project="p", stack="s", preview=False)
    from iacforge.render import run_pulumi_program

    run_pulumi_program(bind(parse_spec(doc()), "pulumi"))
