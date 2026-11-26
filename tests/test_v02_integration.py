"""Cross-agent integration checks for v0.2: examples, pulumi import tokens."""

from pathlib import Path

import pytest

from iacforge import core
from iacforge.adapters import get_adapter
from iacforge.engines.pulumi import PulumiEngine
from iacforge.errors import UnsupportedError
from iacforge.render import bind
from iacforge.spec import parse_spec

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SPECS = sorted(p for p in (ROOT / "examples").rglob("*.y*ml") if ".iacforge" not in p.parts)


@pytest.mark.parametrize("path", EXAMPLE_SPECS, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_example_validates(path):
    assert core.validate(str(path))["valid"] is True


def test_gcp_pulumi_tokens_cover_every_type():
    a = get_adapter("gcp")
    assert set(a.pulumi_types) == set(a.resource_models)
    assert all(t.startswith("gcp:") and t.count(":") == 2 for t in a.pulumi_types.values())


def test_pulumi_import_without_token_is_unsupported(tmp_path):
    stack = parse_spec({"apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "t"},
                        "spec": {"provider": "local", "engine": "pulumi", "resources": [
                            {"name": "f", "type": "file", "properties": {"path": "x", "content": "y"}}]}})
    b = bind(stack)
    with pytest.raises(UnsupportedError, match="pulumi type token"):
        PulumiEngine().import_resource(b, tmp_path, "f", "some-id")
