"""Command-line surface. Thin adapter over ``iacforge.core``.

Output: human-readable by default; ``--json`` (or env ``IACFORGE_OUTPUT=json``) prints one
JSON envelope on stdout: ``{"ok": true, "command": "...", "data": {...}}`` or
``{"ok": false, "command": "...", "error": {"code": "...", "message": "...", "details": ...}}``.
Exit codes are defined in ``iacforge.errors``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from . import core
from .errors import EXIT_ERROR, EXIT_INVALID, EXIT_OK, IacForgeError, NotConfirmedError


def _add_spec_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("spec", nargs="?", default="stack.yaml", help="stack spec file (YAML/JSON), '-' for stdin")
    p.add_argument("--engine", choices=["opentofu", "terraform", "pulumi"], help="override spec.engine")
    p.add_argument("--workdir", help="state/render directory (default: <spec dir>/.iacforge/<stack>/<engine>)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="iacforge",
        description="Provision infrastructure from one provider-neutral spec via OpenTofu/Terraform or Pulumi.",
    )
    ap.add_argument("--json", action="store_true", help="machine-readable JSON envelope on stdout")
    # --json is accepted before or after the subcommand ("iacforge --json plan" == "iacforge plan --json")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="machine-readable JSON envelope on stdout")
    sub = ap.add_subparsers(dest="command", required=True, metavar="COMMAND")
    _orig_add = sub.add_parser
    sub.add_parser = lambda *a, **k: _orig_add(*a, parents=[common], **k)  # type: ignore[method-assign]

    sub.add_parser("version", help="print version, engines and providers")

    p = sub.add_parser("providers", help="list providers and their capabilities")
    p.add_argument("name", nargs="?")

    p = sub.add_parser("schema", help="print JSON Schema (stack, or one provider's properties)")
    p.add_argument("provider", nargs="?")

    sub.add_parser("doctor", help="check host tools and provider readiness")

    p = sub.add_parser("init", help="write a starter stack.yaml")
    p.add_argument("--provider", default="local")
    p.add_argument("--name", default="dev")
    p.add_argument("--engine", default="opentofu", choices=["opentofu", "terraform", "pulumi"])
    p.add_argument("--path", default="stack.yaml")
    p.add_argument("--force", action="store_true")

    for name, hlp in [
        ("validate", "validate a spec against its provider"),
        ("render", "write engine-native files (main.tf.json / Pulumi project) without running"),
        ("plan", "show what apply would change"),
        ("outputs", "show outputs of an applied stack"),
    ]:
        _add_spec_args(sub.add_parser(name, help=hlp))
    for name, hlp in [("apply", "create/update infrastructure"), ("destroy", "delete all stack infrastructure")]:
        p = sub.add_parser(name, help=hlp)
        _add_spec_args(p)
        p.add_argument("-y", "--yes", action="store_true", help="confirm without prompting (required non-interactively)")
    return ap


def _spec_arg(args: argparse.Namespace) -> Any:
    if args.spec == "-":
        return sys.stdin.read()
    return args.spec


def _confirm(args: argparse.Namespace, op: str) -> bool:
    if args.yes:
        return True
    if args.json or not sys.stdin.isatty():
        return False
    ans = input(f"{op} will change real infrastructure for '{args.spec}'. Continue? [y/N] ")
    return ans.strip().lower() in ("y", "yes")


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    c = args.command
    if c == "version":
        return core.version()
    if c == "providers":
        return core.providers(args.name)
    if c == "schema":
        return core.schema(args.provider)
    if c == "doctor":
        return core.doctor()
    if c == "init":
        return core.init(provider=args.provider, name=args.name, engine=args.engine,
                         path=args.path, force=args.force)
    spec = _spec_arg(args)
    kw = {"engine": args.engine, "workdir": args.workdir}
    if c == "validate":
        return core.validate(spec, engine=args.engine)
    if c == "render":
        return core.render(spec, **kw)
    if c == "plan":
        return core.plan(spec, **kw)
    if c == "outputs":
        return core.outputs(spec, **kw)
    if c in ("apply", "destroy"):
        fn = core.apply if c == "apply" else core.destroy
        return fn(spec, confirm=_confirm(args, c), **kw)
    raise IacForgeError(f"unknown command {c}")


def _human(command: str, data: dict[str, Any]) -> str:
    if command == "providers":
        lines = []
        for p in data["providers"]:
            lines.append(f"{p['name']:<10} {p['status']:<9} {p['category']:<6} "
                         f"platforms={','.join(p['platforms'])} engines={','.join(p['engines'])}")
            lines.append(f"{'':<10} types: {', '.join(p['resource_types'])}")
        return "\n".join(lines)
    if command == "doctor":
        lines = [f"platform: {data['platform']}", "engines:"]
        lines += [f"  {k:<10} {'ok' if v else 'missing'}" for k, v in data["engines"].items()]
        lines.append("providers:")
        for p in data["providers"]:
            why = []
            if not p["platform_supported"]:
                why.append("unsupported on this OS")
            if p["missing_tools"]:
                why.append("missing: " + ", ".join(p["missing_tools"]))
            lines.append(f"  {p['name']:<10} {'ready' if p['ready'] else 'not ready'}"
                         + (f" ({'; '.join(why)})" if why else ""))
        return "\n".join(lines)
    if command == "validate":
        out = f"valid: stack '{data['stack']}' provider={data['provider']} engine={data['engine']} " \
              f"resources={len(data['resources'])}"
    elif command in ("render",):
        out = f"rendered to {data['workdir']}: " + ", ".join(data.get("files", []))
    elif command in ("plan", "apply", "destroy"):
        ch = data.get("changes", {})
        out = f"{command}: +{ch.get('add', 0)} ~{ch.get('change', 0)} -{ch.get('destroy', 0)}"
        if data.get("outputs"):
            out += "\noutputs:\n" + json.dumps(data["outputs"], indent=2, sort_keys=True)
    elif command == "outputs":
        out = json.dumps(data.get("outputs", {}), indent=2, sort_keys=True)
    elif command == "init":
        out = f"wrote {data['path']}"
    elif command == "version":
        out = f"iacforge {data['version']}"
    else:
        out = json.dumps(data, indent=2, sort_keys=True)
    for w in data.get("warnings", []) if isinstance(data, dict) else []:
        out += f"\nwarning: {w}"
    return out


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if os.environ.get("IACFORGE_OUTPUT", "").lower() == "json":
        args.json = True
    try:
        data = dispatch(args)
        if args.json:
            print(json.dumps({"ok": True, "command": args.command, "data": data}, sort_keys=True, default=str))
        else:
            print(_human(args.command, data))
        return EXIT_OK
    except IacForgeError as e:
        if args.json:
            print(json.dumps({"ok": False, "command": args.command, "error": e.to_dict()}, sort_keys=True, default=str))
        else:
            print(f"error[{e.code}]: {e.message}", file=sys.stderr)
            if isinstance(e.details, list):
                for d in e.details:
                    print(f"  - {d.get('path', '')}: {d.get('message', d)}" if isinstance(d, dict) else f"  - {d}",
                          file=sys.stderr)
            elif e.details:
                print(f"  {json.dumps(e.details, default=str)}", file=sys.stderr)
            if isinstance(e, NotConfirmedError):
                print("  hint: pass --yes", file=sys.stderr)
        return e.exit_code
    except KeyboardInterrupt:
        return EXIT_INVALID
    except Exception as e:  # unexpected: still emit a structured envelope for agents
        if args.json:
            print(json.dumps({"ok": False, "command": args.command,
                              "error": {"code": "internal", "message": f"{type(e).__name__}: {e}"}}))
        else:
            print(f"internal error: {type(e).__name__}: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
