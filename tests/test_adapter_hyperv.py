import copy

import pytest

from iacforge.adapters.hyperv import ADAPTER, EXAMPLES
from iacforge.errors import SpecError, UnsupportedError
from iacforge.render import bind, render_terraform
from iacforge.spec import parse_spec


def stack(resources, cfg=None):
    return {"apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "x"},
            "spec": {"provider": "hyperv", "providerConfig": cfg or {}, "resources": resources}}


def test_structure_and_deps():
    doc = render_terraform(bind(parse_spec(EXAMPLES[0]), "opentofu"))
    vm = doc["resource"]["hyperv_machine_instance"]["lab1"]
    assert vm["network_adaptors"][0]["switch_name"] == "${hyperv_network_switch.labswitch.name}"
    assert vm["hard_disk_drives"][0]["path"] == "${hyperv_vhd.disk.path}"
    assert vm["memory_startup_bytes"] == 2048 * 1024**2
    assert sorted(vm["depends_on"]) == ["hyperv_network_switch.labswitch", "hyperv_vhd.disk"]
    p = doc["provider"]["hyperv"]
    assert p["port"] == 5986 and "password" not in p


def test_terraform_only_and_platform():
    assert ADAPTER.describe()["engines"] == ["opentofu", "terraform"]
    assert ADAPTER.describe()["platforms"] == ["windows"]
    with pytest.raises(UnsupportedError):
        bind(parse_spec(EXAMPLES[0]), "pulumi")


def test_inline_vhd_extra_block():
    ex = stack([{"name": "v", "type": "vm", "properties": {"vhdPath": "C:\\v.vhdx", "vhdSizeGb": 10, "switch": "Default Switch"}}])
    doc = render_terraform(bind(parse_spec(ex), "opentofu"))
    assert "v_vhd" in doc["resource"]["hyperv_vhd"]
    assert doc["resource"]["hyperv_machine_instance"]["v"]["network_adaptors"][0]["switch_name"] == "Default Switch"


@pytest.mark.parametrize("res", [
    {"name": "s", "type": "switch", "properties": {"type": "External"}},
    {"name": "s", "type": "switch", "properties": {"type": "Bogus"}},
    {"name": "d", "type": "vhd", "properties": {"path": "C:\\d.vhdx"}},
    {"name": "v", "type": "vm", "properties": {"switch": "a", "switchRef": "b"}},
    {"name": "v", "type": "vm", "properties": {"vhdSizeGb": 5}},
    {"name": "v", "type": "vm", "properties": {"generation": 3}},
])
def test_negatives(res):
    with pytest.raises(SpecError):
        bind(parse_spec(stack([res])))


def test_password_passthrough_optional():
    ex = stack(copy.deepcopy(EXAMPLES[0]["spec"]["resources"]), {"user": "u", "password": "p", "useNtlm": False})
    p = render_terraform(bind(parse_spec(ex), "opentofu"))["provider"]["hyperv"]
    assert p["user"] == "u" and p["use_ntlm"] is False
