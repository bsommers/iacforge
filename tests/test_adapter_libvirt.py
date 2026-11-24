import copy

import pytest

from iacforge.adapters.libvirt import EXAMPLES
from iacforge.errors import SpecError
from iacforge.render import bind, render_terraform
from iacforge.spec import parse_spec


def render(ex):
    return render_terraform(bind(parse_spec(ex), "opentofu"))


def test_vm_structure():
    doc = render(EXAMPLES[0])
    res = doc["resource"]
    assert doc["terraform"]["required_providers"]["libvirt"]["version"] == "~> 0.8.1"
    assert doc["provider"]["libvirt"]["uri"] == "qemu:///system"
    assert {"web_base", "web_root"} <= set(res["libvirt_volume"])
    assert "web_cloudinit" in res["libvirt_cloudinit_disk"]
    dom = res["libvirt_domain"]["web"]
    assert dom["network_interface"][0]["network_name"] == "${libvirt_network.labnet.name}"
    assert dom["network_interface"][0]["wait_for_lease"] is True
    assert res["libvirt_volume"]["web_root"]["size"] == 20 * 1024**3
    assert "ssh-ed25519" in res["libvirt_cloudinit_disk"]["web_cloudinit"]["user_data"]
    assert doc["output"]["web__ip"]["value"].endswith("network_interface[0].addresses[0]}")
    assert "libvirt_network.labnet" in dom["depends_on"]


def test_network_modes():
    ex = copy.deepcopy(EXAMPLES[0])
    net = next(r for r in ex["spec"]["resources"] if r["type"] == "network")
    net["properties"]["mode"] = "isolated"
    assert render(ex)["resource"]["libvirt_network"]["labnet"]["mode"] == "none"


@pytest.mark.parametrize("props", [
    {"mode": "bridge"},
    {"mode": "nat"},
    {"mode": "weird", "cidr": "10.0.0.0/24"},
])
def test_network_negatives(props):
    ex = {"apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "x"},
          "spec": {"provider": "libvirt", "resources": [{"name": "n", "type": "network", "properties": props}]}}
    with pytest.raises(SpecError):
        bind(parse_spec(ex))


def test_unknown_ref_and_keys_with_non_cloudconfig():
    ex = copy.deepcopy(EXAMPLES[0])
    vm = next(r for r in ex["spec"]["resources"] if r["type"] == "vm")
    vm["properties"]["networkRef"] = "missing"
    with pytest.raises(SpecError):
        bind(parse_spec(ex))
    vm["properties"]["networkRef"] = "labnet"
    vm["properties"]["cloudInit"] = {"userData": "#!/bin/sh\n"}
    with pytest.raises(SpecError):
        bind(parse_spec(ex))


def test_plain_network_name_no_dep():
    ex = copy.deepcopy(EXAMPLES[0])
    vm = next(r for r in ex["spec"]["resources"] if r["type"] == "vm")
    del vm["properties"]["networkRef"]
    vm["properties"]["network"] = "br-existing"
    dom = render(ex)["resource"]["libvirt_domain"]["web"]
    assert dom["network_interface"][0]["network_name"] == "br-existing"
    assert "libvirt_network.labnet" not in dom["depends_on"]
