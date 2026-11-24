"""docs/agents/spec.schema.json must match the generated schema (run scripts/gen_schema.py)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_committed_schema_matches_generated():
    spec = importlib.util.spec_from_file_location("gen_schema", ROOT / "scripts" / "gen_schema.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    committed = (ROOT / "docs" / "agents" / "spec.schema.json").read_text(encoding="utf-8")
    assert committed == mod.generate(), "stale: run `python scripts/gen_schema.py`"
