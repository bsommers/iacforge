"""Pulumi engine: runs the rendered program through the Pulumi Automation API.

* Backend: local file backend ``file://<workdir>/state`` (no Pulumi Cloud account needed), or
  ``gs://<bucket>/<state key>`` when ``spec.backend.type`` is ``gcs`` (ADR 0005). A remote
  backend requires a non-empty ``PULUMI_CONFIG_PASSPHRASE`` (``SpecError`` otherwise).
* Secrets passphrase: env ``PULUMI_CONFIG_PASSPHRASE`` if set, otherwise the empty string
  (fine for local/dev state; set it explicitly if the stack holds real secrets).
* The program runs in-process with cwd = workdir so relative file paths resolve there.
* ``render`` writes an ejectable project (Pulumi.yaml, __main__.py, stack.json,
  requirements.txt): ``cd <workdir> && pulumi up`` works without iacforge's engine.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..adapters.base import tf_id
from ..errors import EngineError, SpecError, ToolMissingError
from ..render import BoundStack, nest_outputs, run_pulumi_program
from .base import Engine

PROJECT = "iacforge"
INSTALL_HINT = "install the Pulumi CLI (https://www.pulumi.com/docs/install/) and `pip install 'iacforge[pulumi]'`"

MAIN_PY = '''"""Ejected by iacforge: loads stack.json and runs the same program the engine runs."""
import json
from pathlib import Path

from iacforge.render import bind, run_pulumi_program
from iacforge.spec import parse_spec

_spec = json.loads((Path(__file__).parent / "stack.json").read_text(encoding="utf-8"))
run_pulumi_program(bind(parse_spec(_spec), "pulumi"))
'''


@contextlib.contextmanager
def _cwd(path: Path) -> Iterator[None]:
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def _summary_to_changes(summary: dict[str, int] | None) -> dict[str, int]:
    s = summary or {}
    replace = s.get("replace", 0)
    return {"add": s.get("create", 0) + replace, "change": s.get("update", 0),
            "destroy": s.get("delete", 0) + replace}


def backend_url(b: BoundStack, workdir: Path, local_url: str | None = None) -> str:
    """Pulumi backend URL for a bound stack (ADR 0005)."""
    if b.backend.type == "gcs":
        return f"gs://{b.backend.bucket}/{b.state_key}"
    return local_url or f"file://{(workdir / 'state').as_posix()}"


def check_remote_passphrase(b: BoundStack) -> None:
    if b.backend.type != "local" and not os.environ.get("PULUMI_CONFIG_PASSPHRASE"):
        raise SpecError("a remote Pulumi backend requires PULUMI_CONFIG_PASSPHRASE to be set "
                        "and non-empty",
                        details={"hint": "export PULUMI_CONFIG_PASSPHRASE=<secret> (keep it: "
                                         "it encrypts the stack's secrets)"})


class PulumiEngine(Engine):
    name = "pulumi"

    # ------------------------------------------------------------ availability
    def cli(self) -> str:
        exe = self.which("pulumi")
        if not exe:
            raise ToolMissingError("pulumi CLI not found", details={"hint": INSTALL_HINT})
        return exe

    def _sdk(self) -> Any:
        try:
            import pulumi.automation as auto
        except ImportError:
            raise ToolMissingError("pulumi Python SDK not installed",
                                   details={"hint": INSTALL_HINT}) from None
        return auto

    def tool_status(self) -> dict[str, Any]:
        exe = self.which("pulumi")
        version = None
        if exe:
            try:
                r = self.runner([exe, "version"], Path.cwd(), None, 60)
                if r.returncode == 0:
                    version = r.stdout.strip()
            except Exception:
                pass
        try:
            import pulumi  # noqa: F401
            sdk = True
        except ImportError:
            sdk = False
        return {"available": bool(exe) and sdk, "binary": exe, "version": version, "sdk": sdk}

    # ------------------------------------------------------------ render
    def render(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / "Pulumi.yaml").write_text(
            f"name: {PROJECT}\nruntime: python\ndescription: rendered by iacforge\n"
            f"backend:\n  url: {backend_url(b, workdir, 'file://./state')}\n", encoding="utf-8")
        (workdir / "stack.json").write_text(
            json.dumps(b.stack.model_dump(by_alias=True, mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        (workdir / "__main__.py").write_text(MAIN_PY, encoding="utf-8")
        reqs = ["iacforge", "pulumi>=3.100", *b.adapter.pulumi_packages]
        (workdir / "requirements.txt").write_text(
            "\n".join(dict.fromkeys(reqs)) + "\n", encoding="utf-8")
        return {"files": ["Pulumi.yaml", "__main__.py", "requirements.txt", "stack.json"]}

    # ------------------------------------------------------------ stack handle
    def _env(self, workdir: Path, b: BoundStack | None = None) -> dict[str, str]:
        return {
            "PULUMI_CONFIG_PASSPHRASE": os.environ.get("PULUMI_CONFIG_PASSPHRASE", ""),
            "PULUMI_BACKEND_URL": backend_url(b, workdir) if b else f"file://{(workdir / 'state').as_posix()}",
            "PULUMI_SKIP_UPDATE_CHECK": "true",
            "PULUMI_AUTOMATION_API_SKIP_VERSION_CHECK": "true",
        }

    def _open_stack(self, b: BoundStack, workdir: Path) -> Any:
        """Create/select the stack. Overridable in tests."""
        self.cli()
        auto = self._sdk()
        if b.backend.type == "local":
            (workdir / "state").mkdir(parents=True, exist_ok=True)
        env = self._env(workdir, b)
        settings = auto.ProjectSettings(
            name=PROJECT, runtime="python",
            backend=auto.ProjectBackend(url=env["PULUMI_BACKEND_URL"]))
        opts = auto.LocalWorkspaceOptions(work_dir=str(workdir), project_settings=settings,
                                          env_vars=env)
        return auto.create_or_select_stack(
            stack_name=b.stack.name, project_name=PROJECT,
            program=lambda: run_pulumi_program(b), opts=opts)

    @contextlib.contextmanager
    def _stack(self, b: BoundStack, workdir: Path) -> Iterator[Any]:
        check_remote_passphrase(b)
        self.render(b, workdir)
        with _cwd(workdir):
            try:
                yield self._open_stack(b, workdir)
            except (ToolMissingError, EngineError):
                raise
            except Exception as e:
                raise self._wrap(e) from None

    @staticmethod
    def _wrap(e: Exception) -> EngineError:
        text = f"{getattr(e, 'stderr', '') or ''}\n{e}".strip()
        return EngineError(f"pulumi failed: {type(e).__name__}",
                           details={"stderr": "\n".join(text.splitlines()[-40:])})

    def _call(self, fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except (ToolMissingError, EngineError):
            raise
        except Exception as e:
            raise self._wrap(e) from None

    @staticmethod
    def _outputs_from(b: BoundStack, outs: Any) -> dict[str, dict[str, Any]]:
        flat = {k: getattr(v, "value", v) for k, v in (outs or {}).items()}
        back = {tf_id(r.name): r.name for r in b.stack.spec.resources}
        return {back.get(k, k): v for k, v in nest_outputs(flat).items()}

    # ------------------------------------------------------------ operations
    def plan(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        with self._stack(b, workdir) as st:
            r = self._call(st.preview)
        ch = _summary_to_changes(getattr(r, "change_summary", None))
        return {"changes": ch, "resources": [], "has_changes": any(ch.values()),
                "log": getattr(r, "stdout", "")}

    def apply(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        with self._stack(b, workdir) as st:
            r = self._call(st.up)
        summary = getattr(getattr(r, "summary", None), "resource_changes", None)
        return {"changes": _summary_to_changes(summary),
                "outputs": self._outputs_from(b, getattr(r, "outputs", {})),
                "log": getattr(r, "stdout", "")}

    def destroy(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        with self._stack(b, workdir) as st:
            r = self._call(st.destroy)
        summary = getattr(getattr(r, "summary", None), "resource_changes", None)
        return {"changes": _summary_to_changes(summary), "log": getattr(r, "stdout", "")}

    def outputs(self, b: BoundStack, workdir: Path) -> dict[str, Any]:
        with self._stack(b, workdir) as st:
            outs = self._call(st.outputs)
        return {"outputs": self._outputs_from(b, outs)}
