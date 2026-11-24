"""MCP surface (stdio). Thin adapter over ``iacforge.core``: one tool per core operation.

Every tool returns the same envelope as ``iacforge --json``:
``{"ok": true, "command": ..., "data": ...}`` or ``{"ok": false, "command": ..., "error": {...}}``.
The tool functions are plain callables (usable without the ``mcp`` package); ``build_server``
imports ``mcp`` lazily and registers them.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from . import core
from .errors import IacForgeError

SPEC_HELP = "Path to a stack spec file (YAML/JSON), or the inline YAML/JSON text itself."
SAFETY = ("Always run iacforge_validate and iacforge_plan first and review the plan "
          "before calling this.")


def _envelope(command: str, fn: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"ok": True, "command": command, "data": fn()}
    except IacForgeError as e:
        return {"ok": False, "command": command, "error": e.to_dict()}
    except Exception as e:
        return {"ok": False, "command": command,
                "error": {"code": "internal", "message": f"{type(e).__name__}: {e}"}}


def iacforge_version() -> dict[str, Any]:
    """Return iacforge version, supported engines and provider names."""
    return _envelope("version", core.version)


def iacforge_providers(name: str | None = None) -> dict[str, Any]:
    """List providers, their resource types and capabilities (or just one provider by name)."""
    return _envelope("providers", lambda: core.providers(name))


def iacforge_schema(provider: str | None = None) -> dict[str, Any]:
    """Return the JSON Schema of the stack document, or of one provider's config and resources.

    Read this before writing a spec.
    """
    return _envelope("schema", lambda: core.schema(provider))


def iacforge_doctor() -> dict[str, Any]:
    """Check host tools (tofu, terraform, pulumi, docker, ...) and per-provider readiness."""
    return _envelope("doctor", core.doctor)


def iacforge_validate(spec: str, engine: str | None = None) -> dict[str, Any]:
    """Validate a stack spec against its provider without touching anything.

    spec: file path or inline YAML/JSON text. engine: opentofu|terraform|pulumi override.
    Run this, then iacforge_plan, before iacforge_apply.
    """
    return _envelope("validate", lambda: core.validate(spec, engine))


def iacforge_render(spec: str, engine: str | None = None,
                    workdir: str | None = None) -> dict[str, Any]:
    """Write engine-native files (main.tf.json or a Pulumi project) to workdir; runs nothing."""
    return _envelope("render", lambda: core.render(spec, engine, workdir))


def iacforge_plan(spec: str, engine: str | None = None,
                  workdir: str | None = None) -> dict[str, Any]:
    """Show what apply would change. Read-only against infrastructure. Review before apply."""
    return _envelope("plan", lambda: core.plan(spec, engine, workdir))


def iacforge_outputs(spec: str, engine: str | None = None,
                     workdir: str | None = None) -> dict[str, Any]:
    """Show outputs of an already-applied stack."""
    return _envelope("outputs", lambda: core.outputs(spec, engine, workdir))


def iacforge_apply(spec: str, engine: str | None = None, workdir: str | None = None,
                   confirm: bool = False) -> dict[str, Any]:
    """Create/update REAL infrastructure. Requires confirm=true. Run iacforge_validate and
    iacforge_plan first and review the plan; without confirm=true this returns a
    not_confirmed error and changes nothing."""
    return _envelope("apply", lambda: core.apply(spec, engine, workdir, confirm=confirm))


def iacforge_destroy(spec: str, engine: str | None = None, workdir: str | None = None,
                     confirm: bool = False) -> dict[str, Any]:
    """DELETE all infrastructure of the stack. Requires confirm=true. Run iacforge_plan first
    and review; without confirm=true this returns a not_confirmed error and changes nothing."""
    return _envelope("destroy", lambda: core.destroy(spec, engine, workdir, confirm=confirm))


TOOLS: tuple[Callable[..., dict[str, Any]], ...] = (
    iacforge_version, iacforge_providers, iacforge_schema, iacforge_doctor, iacforge_validate,
    iacforge_render, iacforge_plan, iacforge_outputs, iacforge_apply, iacforge_destroy,
)


def build_server():
    """Create the FastMCP server. Raises RuntimeError with install hint if ``mcp`` is missing."""
    try:
        try:
            from mcp.server.mcpserver import MCPServer as FastMCP  # mcp >= 2
        except ImportError:
            from mcp.server.fastmcp import FastMCP  # mcp 1.x
    except ImportError as e:
        raise RuntimeError(
            "the 'mcp' package is required for iacforge-mcp; "
            "install it with: pip install 'iacforge[mcp]'") from e
    server = FastMCP("iacforge")
    for fn in TOOLS:
        server.tool()(fn)
    return server


def main(argv: list[str] | None = None) -> None:
    import argparse

    argparse.ArgumentParser(
        prog="iacforge-mcp",
        description="iacforge MCP server (stdio). Configure it in an MCP client, e.g. "
        "`claude mcp add iacforge -- iacforge-mcp`. Tools: " + ", ".join(f.__name__ for f in TOOLS),
    ).parse_args(argv)
    try:
        server = build_server()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(3) from e
    server.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main()
