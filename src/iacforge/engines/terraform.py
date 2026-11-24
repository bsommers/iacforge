"""OpenTofu / Terraform engine: writes ``main.tf.json`` and drives the CLI.

Binary selection: env ``IACFORGE_TF_BINARY`` (name or path) wins; otherwise flavor
``opentofu`` prefers ``tofu`` then ``terraform``; flavor ``terraform`` the reverse.
State is the default local backend inside the workdir.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from ..adapters.base import tf_id
from ..errors import EngineError, ToolMissingError
from ..render import BoundStack, nest_outputs, terraform_json
from .base import Engine, ProcResult, Runner, Which

MAIN_FILE = "main.tf.json"
PLAN_FILE = "tfplan"
TIMEOUT = 3600.0
COMMON = ["-input=false", "-no-color"]
ENV_OVERRIDE = "IACFORGE_TF_BINARY"


def _tail(text: str, n: int = 40) -> str:
    return "\n".join(text.strip().splitlines()[-n:])


class TerraformEngine(Engine):
    def __init__(self, flavor: str = "opentofu", runner: Runner | None = None,
                 which: Which | None = None, timeout: float = TIMEOUT):
        super().__init__(runner, which)
        self.flavor = flavor
        self.name = flavor
        self.timeout = timeout

    # ------------------------------------------------------------ binary
    def _candidates(self) -> list[str]:
        override = os.environ.get(ENV_OVERRIDE)
        if override:
            return [override]
        return ["tofu", "terraform"] if self.flavor == "opentofu" else ["terraform", "tofu"]

    def binary(self) -> str:
        for c in self._candidates():
            found = self.which(c)
            if found:
                return found
        raise ToolMissingError(
            f"no OpenTofu/Terraform binary found (looked for: {', '.join(self._candidates())})",
            details={"hint": "install OpenTofu (https://opentofu.org/docs/intro/install/) or set "
                             f"{ENV_OVERRIDE}"},
        )

    def tool_status(self) -> dict[str, Any]:
        try:
            exe = self.binary()
        except ToolMissingError:
            return {"available": False, "binary": None, "version": None}
        version = None
        try:
            r = self.runner([exe, "version", "-json"], Path.cwd(), self._env(), 60)
            if r.returncode == 0:
                version = json.loads(r.stdout).get("terraform_version")
        except Exception:
            pass
        return {"available": True, "binary": exe, "version": version}

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _env() -> dict[str, str]:
        return {"TF_IN_AUTOMATION": "1", "TF_INPUT": "0", "CHECKPOINT_DISABLE": "1"}

    def _run(self, exe: str, args: list[str], wd: Path, ok: tuple[int, ...] = (0,)) -> ProcResult:
        cmd = [exe, *args]
        try:
            r = self.runner(cmd, wd, self._env(), self.timeout)
        except Exception as e:  # timeout, OSError
            raise EngineError(f"{Path(exe).name} {args[0]} failed to run: {type(e).__name__}: {e}",
                              details={"command": cmd}) from None
        if r.returncode not in ok:
            raise EngineError(
                f"{Path(exe).name} {args[0]} failed (exit {r.returncode})",
                details={"command": cmd, "exit_code": r.returncode,
                         "stderr": _tail(r.stderr), "stdout": _tail(r.stdout, 10)},
            )
        return r

    def render(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / MAIN_FILE).write_text(terraform_json(b), encoding="utf-8")
        return {"files": [MAIN_FILE]}

    def _init(self, exe: str, wd: Path) -> str:
        """`init`, skipped when the config and lock file are unchanged since the last init."""
        main = wd / MAIN_FILE
        lock = wd / ".terraform.lock.hcl"
        stamp = wd / ".terraform" / "iacforge-init.sha256"
        digest = hashlib.sha256(main.read_bytes()).hexdigest()
        if lock.exists() and stamp.exists() and stamp.read_text().strip() == digest:
            return ""
        r = self._run(exe, ["init", *COMMON], wd)
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(digest)
        return r.stdout

    def _prepare(self, b: BoundStack, workdir: Path) -> tuple[str, Path, str]:
        exe = self.binary()
        self.render(b, workdir)
        return exe, workdir, self._init(exe, workdir)

    @staticmethod
    def _count(changes: list[dict[str, Any]]) -> tuple[dict[str, int], list[dict[str, Any]]]:
        counts = {"add": 0, "change": 0, "destroy": 0}
        items = []
        for rc in changes:
            actions = rc.get("change", {}).get("actions", [])
            if actions in (["no-op"], ["read"]) or not actions:
                continue
            if "create" in actions:
                counts["add"] += 1
            if "update" in actions:
                counts["change"] += 1
            if "delete" in actions:
                counts["destroy"] += 1
            items.append({"address": rc.get("address"), "actions": actions})
        return counts, items

    def _stack_outputs(self, b: BoundStack, exe: str, wd: Path) -> dict[str, dict[str, Any]]:
        r = self._run(exe, ["output", "-json", "-no-color"], wd)
        try:
            raw = json.loads(r.stdout or "{}")
        except json.JSONDecodeError:
            raise EngineError("could not parse `output -json`", details={"stdout": _tail(r.stdout)}) from None
        flat = {k: v.get("value") if isinstance(v, dict) else v for k, v in raw.items()}
        nested = nest_outputs(flat)
        back = {tf_id(r_.name): r_.name for r_ in b.stack.spec.resources}
        return {back.get(k, k): v for k, v in nested.items()}

    # ------------------------------------------------------------ operations
    def plan(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        exe, wd, log = self._prepare(b, workdir)
        r = self._run(exe, ["plan", f"-out={PLAN_FILE}", *COMMON, "-detailed-exitcode"], wd, ok=(0, 2))
        s = self._run(exe, ["show", "-json", "-no-color", PLAN_FILE], wd)
        try:
            doc = json.loads(s.stdout)
        except json.JSONDecodeError:
            raise EngineError("could not parse `show -json` output", details={"stdout": _tail(s.stdout)}) from None
        counts, items = self._count(doc.get("resource_changes", []))
        return {"changes": counts, "resources": items, "has_changes": r.returncode == 2,
                "log": log + r.stdout}

    def apply(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        exe, wd, log = self._prepare(b, workdir)
        r = self._run(exe, ["apply", "-auto-approve", *COMMON], wd)
        changes = self._parse_summary(r.stdout)
        return {"changes": changes, "outputs": self._stack_outputs(b, exe, wd), "log": log + r.stdout}

    def destroy(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        exe, wd, log = self._prepare(b, workdir)
        r = self._run(exe, ["destroy", "-auto-approve", *COMMON], wd)
        return {"changes": self._parse_summary(r.stdout), "log": log + r.stdout}

    def outputs(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        exe = self.binary()
        if not (workdir / MAIN_FILE).exists():
            self.render(b, workdir)
        self._init(exe, workdir)
        return {"outputs": self._stack_outputs(b, exe, workdir)}

    @staticmethod
    def _parse_summary(text: str) -> dict[str, int]:
        """Parse 'Apply complete! Resources: 1 added, 0 changed, 0 destroyed.' (zeros if absent)."""
        import re

        out = {"add": 0, "change": 0, "destroy": 0}
        m = re.search(r"Resources: (\d+) added, (\d+) changed, (\d+) destroyed", text)
        if m:
            out = {"add": int(m[1]), "change": int(m[2]), "destroy": int(m[3])}
            return out
        m = re.search(r"Destroy complete! Resources: (\d+) destroyed", text)
        if m:
            out["destroy"] = int(m[1])
        return out
