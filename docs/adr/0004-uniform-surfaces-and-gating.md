# ADR 0004: Every operation exists once in core and is exposed on CLI, Python and MCP

Status: accepted (2026-11-24)

## Decision
`iacforge.core` implements every operation and returns JSON-able dicts. The CLI
(`--json` envelope + stable exit codes), the Python API and the MCP server are thin
adapters. `src/iacforge/surfaces.py` lists every operation and its name on each surface;
`tests/test_surface_parity.py` fails if a surface is missing one.

`apply` and `destroy` are gated **in core**: they need `confirm=True` (CLI `--yes`, MCP
`confirm: true`). Remote surfaces can't get around the gate.

## Consequences
Agents get the same validation, errors and gating as humans. Error `code` strings and
exit codes are a public contract: changing them is a breaking change.
