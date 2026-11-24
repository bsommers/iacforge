"""Core operations: the single implementation behind every surface (CLI, Python API, MCP).

Every function returns a JSON-serialisable dict and raises ``IacForgeError`` subclasses on
failure. Surfaces only translate input and render output; they must not add behaviour.
Mutating operations (apply, destroy) are gated here: they require ``confirm=True``.
"""

from __future__ import annotations

import platform
import shutil
from pathlib import Path
from typing import Any

from . import __version__
from .adapters import all_adapters, get_adapter, provider_names
from .engines import ENGINE_NAMES, get_engine
from .engines.base import Runner
from .errors import NotConfirmedError, SpecError
from .render import BoundStack, bind
from .spec import StackSpec, load_spec, load_spec_text, parse_spec, spec_json_schema

SpecInput = "str | Path | dict | StackSpec"

HOST_TOOLS = (
    "tofu", "terraform", "pulumi", "docker", "podman", "virsh", "qemu-img",
    "multipass", "powershell", "pwsh", "aws", "gcloud",
)


def host_platform() -> str:
    s = platform.system().lower()
    return {"darwin": "darwin", "windows": "windows"}.get(s, "linux" if s == "linux" else s)


def _load(spec: Any) -> StackSpec:
    if isinstance(spec, StackSpec):
        return spec
    if isinstance(spec, dict):
        return parse_spec(spec)
    if isinstance(spec, Path):
        return load_spec(spec)
    if isinstance(spec, str):
        # a path if it exists or looks like a file name, otherwise inline YAML/JSON text
        if "\n" not in spec and (Path(spec).exists() or spec.endswith((".yaml", ".yml", ".json"))):
            return load_spec(spec)
        return load_spec_text(spec)
    raise SpecError(f"unsupported spec input type: {type(spec).__name__}")


def _spec_dir(spec: Any) -> Path:
    if isinstance(spec, (str, Path)) and "\n" not in str(spec) and Path(spec).exists():
        return Path(spec).resolve().parent
    return Path.cwd()


def resolve_workdir(spec: Any, stack: StackSpec, workdir: str | Path | None) -> Path:
    """Default workdir: <spec dir>/.iacforge/<stack name>/<engine>."""
    if workdir is not None:
        return Path(workdir).resolve()
    return _spec_dir(spec) / ".iacforge" / stack.name / stack.spec.engine


def _bind(spec: Any, engine: str | None) -> tuple[StackSpec, BoundStack]:
    stack = _load(spec)
    b = bind(stack, engine)
    plat = host_platform()
    if plat not in b.adapter.platforms:
        b.warnings.append(
            f"provider '{b.adapter.name}' does not run on host platform '{plat}' "
            f"(supported: {', '.join(sorted(b.adapter.platforms))}); render works, apply will likely fail"
        )
    return stack, b


def _envelope_base(b: BoundStack, workdir: Path | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {
        "stack": b.stack.name,
        "provider": b.adapter.name,
        "engine": b.engine,
        "resources": [r.name for r in b.order],
    }
    if workdir is not None:
        d["workdir"] = str(workdir)
    if b.warnings:
        d["warnings"] = list(b.warnings)
    return d


# ----------------------------------------------------------------- read-only operations

def version() -> dict[str, Any]:
    return {"version": __version__, "engines": list(ENGINE_NAMES), "providers": provider_names()}


def providers(name: str | None = None) -> dict[str, Any]:
    if name:
        return {"providers": [get_adapter(name).describe()]}
    return {"providers": [a.describe() for a in all_adapters()]}


def schema(provider: str | None = None) -> dict[str, Any]:
    """JSON Schema of the stack document, or of one provider's config + resource properties."""
    if provider:
        return {"schema": get_adapter(provider).json_schema()}
    return {"schema": spec_json_schema()}


def validate(spec: Any, engine: str | None = None) -> dict[str, Any]:
    _, b = _bind(spec, engine)
    return {**_envelope_base(b), "valid": True}


def doctor(which=shutil.which) -> dict[str, Any]:
    """Report host tools and, per provider, whether it is ready to apply on this host."""
    plat = host_platform()
    tools = {t: which(t) for t in HOST_TOOLS}
    engines = {
        "opentofu": bool(tools["tofu"]),
        "terraform": bool(tools["terraform"] or tools["tofu"]),
        "pulumi": bool(tools["pulumi"]),
    }
    try:
        import pulumi  # noqa: F401

        pulumi_sdk = True
    except Exception:
        pulumi_sdk = False
    provs = []
    for a in all_adapters():
        missing = [t for t in a.required_tools if not tools.get(t) and not which(t)]
        on_platform = plat in a.platforms
        provs.append({
            "name": a.name,
            "status": a.status,
            "platform_supported": on_platform,
            "missing_tools": missing,
            "ready": on_platform and not missing and (engines["opentofu"] or engines["terraform"]),
        })
    return {
        "platform": plat,
        "tools": {k: v for k, v in tools.items()},
        "engines": engines,
        "pulumi_sdk_installed": pulumi_sdk,
        "providers": provs,
    }


def render(spec: Any, engine: str | None = None, workdir: str | Path | None = None,
           runner: Runner | None = None) -> dict[str, Any]:
    _, b = _bind(spec, engine)
    wd = resolve_workdir(spec, b.stack, workdir)
    eng = get_engine(b.engine, runner=runner)
    res = eng.render(b, wd)
    return {**_envelope_base(b, wd), **res}


def plan(spec: Any, engine: str | None = None, workdir: str | Path | None = None,
         runner: Runner | None = None) -> dict[str, Any]:
    _, b = _bind(spec, engine)
    wd = resolve_workdir(spec, b.stack, workdir)
    eng = get_engine(b.engine, runner=runner)
    return {**_envelope_base(b, wd), **eng.plan(b, wd)}


def outputs(spec: Any, engine: str | None = None, workdir: str | Path | None = None,
            runner: Runner | None = None) -> dict[str, Any]:
    _, b = _bind(spec, engine)
    wd = resolve_workdir(spec, b.stack, workdir)
    eng = get_engine(b.engine, runner=runner)
    return {**_envelope_base(b, wd), **eng.outputs(b, wd)}


# ----------------------------------------------------------------- mutating operations

def _gate(op: str, confirm: bool, b: BoundStack) -> None:
    if not confirm:
        raise NotConfirmedError(
            f"'{op}' changes real infrastructure; re-run with confirmation "
            f"(CLI: --yes, Python: confirm=True, MCP: confirm=true)",
            details={"stack": b.stack.name, "provider": b.adapter.name},
        )


def apply(spec: Any, engine: str | None = None, workdir: str | Path | None = None,
          confirm: bool = False, runner: Runner | None = None) -> dict[str, Any]:
    _, b = _bind(spec, engine)
    _gate("apply", confirm, b)
    wd = resolve_workdir(spec, b.stack, workdir)
    eng = get_engine(b.engine, runner=runner)
    return {**_envelope_base(b, wd), **eng.apply(b, wd)}


def destroy(spec: Any, engine: str | None = None, workdir: str | Path | None = None,
            confirm: bool = False, runner: Runner | None = None) -> dict[str, Any]:
    _, b = _bind(spec, engine)
    _gate("destroy", confirm, b)
    wd = resolve_workdir(spec, b.stack, workdir)
    eng = get_engine(b.engine, runner=runner)
    return {**_envelope_base(b, wd), **eng.destroy(b, wd)}


# ----------------------------------------------------------------- scaffolding

STARTERS: dict[str, dict[str, Any]] = {
    "local": {"provider": "local", "resources": [
        {"name": "hello", "type": "file", "properties": {"path": "out/hello.txt", "content": "hello from iacforge\n"}}]},
    "docker": {"provider": "docker", "resources": [
        {"name": "net", "type": "network", "properties": {}},
        {"name": "web", "type": "container", "properties": {
            "image": "nginx:1.27-alpine", "ports": [{"internal": 80, "external": 8080}], "networks": ["net"]}}]},
}


def init(provider: str = "local", name: str = "dev", engine: str = "opentofu",
         path: str | Path | None = None, force: bool = False) -> dict[str, Any]:
    """Write a starter stack.yaml for a provider. Returns the path and document."""
    import yaml

    get_adapter(provider)  # validate name
    body = STARTERS.get(provider, {"provider": provider, "resources": []})
    doc = {
        "apiVersion": "iacforge/v1",
        "kind": "Stack",
        "metadata": {"name": name},
        "spec": {"provider": body["provider"], "engine": engine, "providerConfig": {},
                 "resources": body["resources"]},
    }
    parse_spec(doc)
    out = Path(path or "stack.yaml")
    if out.exists() and not force:
        raise SpecError(f"{out} already exists (use force/--force to overwrite)")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return {"path": str(out), "document": doc}
