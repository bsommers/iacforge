#!/usr/bin/env python3
"""Regenerate docs/agents/spec.schema.json from `iacforge schema` (deterministic, sorted keys).

Usage: python scripts/gen_schema.py          # rewrite the file
       python scripts/gen_schema.py --check  # exit 1 if the committed file is stale
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "agents" / "spec.schema.json"


def generate() -> str:
    from iacforge import core

    return json.dumps(core.schema()["schema"], indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    text = generate()
    if "--check" in argv:
        return 0 if OUT.exists() and OUT.read_text(encoding="utf-8") == text else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
