"""Shared contract suite: runs against EVERY registered provider adapter.

Every adapter module must export ``EXAMPLES``: a list of minimal valid stack documents
(dicts) that together exercise every resource type it supports.
"""

import importlib
import json
import subprocess

import pytest

from iacforge.adapters import ADAPTER_MODULES, get_adapter, provider_names
from iacforge.adapters.base import TF, ProviderAdapter
from iacforge.render import bind, render_terraform
from iacforge.spec import parse_spec

from .conftest import tf_binary

NAMES = provider_names()


def examples(name):
    mod = importlib.import_module(ADAPTER_MODULES[name], "iacforge.adapters")
    return getattr(mod, "EXAMPLES", [])


@pytest.mark.parametrize("name", NAMES)
def test_registered_and_described(name):
    a = get_adapter(name)
    assert isinstance(a, ProviderAdapter)
    d = a.describe()
    assert d["name"] == name and d["description"] and d["resource_types"]
    assert d["status"] in ("stable", "beta", "scaffold")
    assert set(d["platforms"]) <= {"linux", "darwin", "windows"}
    json.dumps(a.json_schema())


@pytest.mark.parametrize("name", NAMES)
def test_every_type_has_tf_type(name):
    a = get_adapter(name)
    if TF in a.engines:
        assert set(a.resource_models) <= set(a.tf_types)
        assert a.tf_required_providers


@pytest.mark.parametrize("name", NAMES)
def test_examples_cover_all_types(name):
    exs = examples(name)
    assert exs, f"{name} must export EXAMPLES"
    covered = {r["type"] for ex in exs for r in ex["spec"]["resources"]}
    assert covered == set(get_adapter(name).resource_models)


@pytest.mark.parametrize("name", NAMES)
def test_examples_render_deterministically(name):
    for ex in examples(name):
        b = bind(parse_spec(ex), "opentofu")
        a1 = json.dumps(render_terraform(b), sort_keys=True)
        a2 = json.dumps(render_terraform(bind(parse_spec(ex), "opentofu")), sort_keys=True)
        assert a1 == a2


@pytest.mark.parametrize("name", NAMES)
def test_unknown_property_rejected(name):
    from iacforge.errors import SpecError

    ex = json.loads(json.dumps(examples(name)[0]))
    ex["spec"]["resources"][0]["properties"]["definitely_not_a_field"] = 1
    with pytest.raises(SpecError):
        bind(parse_spec(ex))


@pytest.mark.tofu
@pytest.mark.parametrize("name", NAMES)
def test_examples_pass_tofu_validate(name, tmp_path):
    """Downstream check: the real tofu/terraform must accept the rendered JSON."""
    binary = tf_binary()
    if not binary:
        pytest.skip("tofu/terraform not installed")
    for i, ex in enumerate(examples(name)):
        d = tmp_path / f"ex{i}"
        d.mkdir()
        (d / "main.tf.json").write_text(json.dumps(render_terraform(bind(parse_spec(ex), "opentofu"))))
        init = subprocess.run([binary, "init", "-backend=false", "-input=false", "-no-color"],
                              cwd=d, capture_output=True, text=True, timeout=600)
        if init.returncode != 0 and ("registry" in init.stderr.lower() or "could not" in init.stderr.lower()):
            pytest.skip(f"provider download failed (offline?): {init.stderr[-300:]}")
        assert init.returncode == 0, init.stderr
        v = subprocess.run([binary, "validate", "-no-color", "-json"], cwd=d, capture_output=True, text=True)
        assert v.returncode == 0, v.stdout + v.stderr
