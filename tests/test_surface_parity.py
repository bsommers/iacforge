import argparse
import inspect

from iacforge import cli, core
from iacforge.surfaces import NON_OPERATIONS, OPERATIONS


def _core_ops():
    return {
        n for n, f in inspect.getmembers(core, inspect.isfunction)
        if not n.startswith("_") and f.__module__ == core.__name__ and n not in NON_OPERATIONS
    }


def _cli_commands():
    ap = cli.build_parser()
    for a in ap._actions:
        if isinstance(a, argparse._SubParsersAction):
            return set(a.choices)
    raise AssertionError("no subparsers")


def _mcp_tools():
    from iacforge import mcp_server
    return {f.__name__ for f in mcp_server.TOOLS}


def test_every_core_op_in_table():
    assert _core_ops() == {o.core for o in OPERATIONS}


def test_cli_matches_table():
    expected = {o.cli for o in OPERATIONS if o.cli}
    assert expected <= _cli_commands()
    assert _cli_commands() <= expected


def test_exclusions_documented():
    for o in OPERATIONS:
        if o.cli is None or o.mcp is None:
            assert o.exclusion, f"{o.core} missing a surface without a documented reason"


def test_mcp_matches_table():
    expected = {o.mcp for o in OPERATIONS if o.mcp}
    assert _mcp_tools() == expected


def test_mcp_registered_in_fastmcp():
    import asyncio

    import pytest
    pytest.importorskip("mcp")
    from iacforge import mcp_server
    tools = asyncio.run(mcp_server.build_server().list_tools())
    assert {t.name for t in tools} == {o.mcp for o in OPERATIONS if o.mcp}
