import pytest

from iacforge.adapters.multipass import ADAPTER, EXAMPLES
from iacforge.errors import SpecError, UnsupportedError
from iacforge.render import bind, render_terraform
from iacforge.spec import parse_spec


def stack(props):
    return {"apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "x"},
            "spec": {"provider": "multipass", "resources": [{"name": "dev-1", "type": "vm", "properties": props}]}}


def test_structure_with_cloudinit():
    doc = render_terraform(bind(parse_spec(EXAMPLES[0]), "opentofu"))
    vm = doc["resource"]["multipass_instance"]["dev"]
    assert vm["memory"] == "2G" and vm["disk"] == "10G" and vm["cpus"] == 2
    assert vm["cloudinit_file"] == "${local_file.dev_cloudinit.filename}"
    assert "packages" in doc["resource"]["local_file"]["dev_cloudinit"]["content"]
    assert set(doc["terraform"]["required_providers"]) == {"multipass", "local"}
    assert doc["output"]["dev__ipv4"]["value"] == "${multipass_instance.dev.ipv4}"


def test_defaults_no_cloudinit():
    doc = render_terraform(bind(parse_spec(stack({})), "opentofu"))
    vm = doc["resource"]["multipass_instance"]["dev_1"]
    assert vm["image"] == "24.04" and "cloudinit_file" not in vm and "local_file" not in doc["resource"]


def test_fractional_memory():
    doc = render_terraform(bind(parse_spec(stack({"memoryGb": 1.5})), "opentofu"))
    assert doc["resource"]["multipass_instance"]["dev_1"]["memory"] == "1536M"


def test_platforms_engines():
    assert set(ADAPTER.describe()["platforms"]) == {"linux", "darwin", "windows"}
    with pytest.raises(UnsupportedError):
        bind(parse_spec(stack({})), "pulumi")


@pytest.mark.parametrize("props", [{"cpus": 0}, {"memory": "lots"}, {"memory": "2G", "memoryGb": 2}, {"diskGb": 0}])
def test_negatives(props):
    with pytest.raises(SpecError):
        bind(parse_spec(stack(props)))
