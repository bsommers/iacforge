"""Single table of core operations and the surface entry point for each.

``tests/test_surface_parity.py`` fails if a public core operation is missing here, or if the
CLI parser / MCP server lacks an entry listed here. Exclusions must be documented.
"""

from __future__ import annotations

from typing import NamedTuple


class Operation(NamedTuple):
    core: str                 # function name in iacforge.core
    cli: str | None           # CLI subcommand
    mcp: str | None           # MCP tool name
    exclusion: str = ""       # why a surface is intentionally absent


OPERATIONS: tuple[Operation, ...] = (
    Operation("version", "version", "iacforge_version"),
    Operation("providers", "providers", "iacforge_providers"),
    Operation("schema", "schema", "iacforge_schema"),
    Operation("doctor", "doctor", "iacforge_doctor"),
    Operation("validate", "validate", "iacforge_validate"),
    Operation("render", "render", "iacforge_render"),
    Operation("plan", "plan", "iacforge_plan"),
    Operation("outputs", "outputs", "iacforge_outputs"),
    Operation("apply", "apply", "iacforge_apply"),
    Operation("destroy", "destroy", "iacforge_destroy"),
    Operation("init", "init", None,
              "scaffolds a file in the server's cwd; agents write specs directly "
              "(see iacforge_schema), so MCP exposes no file-scaffolding tool"),
)

# Public callables in iacforge.core that are helpers, not operations.
NON_OPERATIONS = frozenset({"host_platform", "resolve_workdir"})
