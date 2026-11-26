"""Engine contract. An engine turns a BoundStack into real infrastructure.

Engines own all process execution and state. They receive a ``Runner`` so tests can
substitute a fake without touching tofu/terraform/pulumi.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..render import BoundStack


@dataclass
class ProcResult:
    returncode: int
    stdout: str
    stderr: str


class Runner(Protocol):
    def __call__(self, args: list[str], cwd: Path, env: dict[str, str] | None = None,
                 timeout: float | None = None) -> ProcResult: ...


def subprocess_runner(args: list[str], cwd: Path, env: dict[str, str] | None = None,
                      timeout: float | None = None) -> ProcResult:
    """Default runner. Never uses a shell; args are passed as a list."""
    full_env = {**os.environ, **(env or {})}
    p = subprocess.run(args, cwd=str(cwd), env=full_env, capture_output=True, text=True,
                       timeout=timeout, check=False)
    return ProcResult(p.returncode, p.stdout, p.stderr)


Which = Callable[[str], "str | None"]


class Engine:
    """Lifecycle: render -> plan -> apply -> outputs -> destroy. All return JSON-able dicts."""

    name: str = ""

    def __init__(self, runner: Runner | None = None, which: Which | None = None):
        self.runner: Runner = runner or subprocess_runner
        self.which: Which = which or shutil.which

    def tool_status(self) -> dict[str, Any]:
        """{"available": bool, "binary": path|None, "version": str|None}"""
        raise NotImplementedError

    def render(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        """Write engine-native files into workdir. Returns {"files": [relative paths]}."""
        raise NotImplementedError

    def plan(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        """Returns {"changes": {"add": n, "change": n, "destroy": n}, "resources": [...], "log": str}."""
        raise NotImplementedError

    def apply(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        """Returns {"changes": {...}, "outputs": {resource: {key: value}}, "log": str}."""
        raise NotImplementedError

    def destroy(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        """Returns {"changes": {...}, "log": str}."""
        raise NotImplementedError

    def outputs(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        """Returns {"outputs": {resource: {key: value}}}."""
        raise NotImplementedError

    def import_resource(self, b: BoundStack, workdir: Path, resource: str, import_id: str) -> dict[str, Any]:
        """Adopt an existing resource into state (ADR 0006). Returns {"address": str, "log": str}."""
        raise NotImplementedError
