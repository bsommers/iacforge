# AGENTS.md

Guidance for AI coding agents working ON this repository. (To *use* iacforge to provision
infrastructure, read `docs/agents/using-iacforge.md` instead.)

## What this is

`iacforge` is provider-neutral IaC: one YAML stack spec (`apiVersion: iacforge/v1`) is validated
by a provider adapter and rendered/executed by an engine (OpenTofu/Terraform JSON, or Pulumi).
Humans use the CLI, programs use `iacforge.core`, AI agents use the MCP server. Python >= 3.10.

## Commands (all verified)

```bash
uv venv && uv pip install -e '.[dev,mcp]'   # setup; add extras like .[pulumi] if needed
ruff check .                                # lint (CI gate); use .venv/bin/ruff if venv not active
pytest -q                                   # full suite (needs network + tofu for `tofu` tests)
pytest -q -m "not tofu"                     # offline subset (CI runs this too)
pytest -q tests/test_core_cli.py::test_apply_without_yes_exit_5   # one test
python scripts/gen_schema.py                # regenerate docs/agents/spec.schema.json
iacforge --json validate stack.yaml         # CLI; `iacforge-mcp` runs the MCP server
```

Markers: `docker` (needs daemon), `tofu` (needs tofu/terraform + network), `pulumi` (needs CLI).

## Architecture map

- `src/iacforge/core.py` - the ONLY implementation of operations (version, providers, schema,
  doctor, validate, render, plan, outputs, apply, destroy, init). Returns JSON-able dicts,
  raises `IacForgeError`. Owns the `confirm` gate for apply/destroy.
- `cli.py` / `mcp_server.py` - thin surfaces over core; envelope `{ok, command, data|error}`.
- `surfaces.py` - table mapping each core op to its CLI command and MCP tool.
- `spec.py` - generic stack document models, YAML/JSON loading, `spec_json_schema()`.
- `render.py` - `bind()`: spec + adapter -> `BoundStack` (validation, dependency order, warnings).
- `adapters/base.py` - `ProviderAdapter` contract; `adapters/<name>.py` one per provider;
  registry in `adapters/__init__.py` (`ADAPTER_MODULES`).
- `engines/{base,terraform,pulumi}.py` - run tools, own all side effects and state/workdir.
- `errors.py` - typed errors, stable `code` and process exit codes.
- `tests/` - per-adapter, contract (`test_adapter_contract.py`), engine, surface parity, MCP.
- `docs/` - ROADMAP, ADRs, `docs/agents/` (agent usage guide + generated JSON Schema).

## Invariants (do not break)

1. Adapters are pure: validated spec in, engine-native description out. No subprocess, no
   filesystem, no network, no state.
2. Engines own side effects (processes, workdir, state). Nothing else shells out.
3. The confirmation gate lives in `core` (`_gate`), never only in a surface.
4. Rendering is deterministic: same spec -> byte-identical output (sorted keys, no timestamps).
5. Every adapter module exports `ADAPTER` and a non-empty `EXAMPLES` list (contract tests use it).
6. Every core operation exists on every surface, listed in `surfaces.py`. A deliberate gap needs a
   written `exclusion` string (see `init` on MCP). `tests/test_surface_parity.py` enforces this.
7. Error `code` values and exit codes (`errors.py`: 0 ok, 1 internal, 2 invalid, 3 tool missing,
   4 engine failed, 5 not confirmed) and the JSON envelope shape are public API. Add, don't rename.
8. Surfaces add no behaviour; if CLI and MCP differ, the logic belongs in core.
9. Property models extend `Props` (`extra="forbid"`) so typos are errors.

## Pitfalls

- `tofu` tests download providers (`hashicorp/local` etc.); offline they fail, use `-m "not tofu"`.
- The `pulumi` CLI is usually absent; pulumi tests skip and `plan --engine pulumi` returns `tool_missing`.
- `ProviderAdapter.references()` receives only one resource's props, no stack access. Cross-resource
  links therefore use explicit `*Ref` / `imageFrom`-style fields; dependencies are derived from them.
- Relative local paths (e.g. `local` file `path`) resolve against the engine workdir
  (`<spec dir>/.iacforge/<stack>/<engine>`), not the cwd.
- `.iacforge/` holds tfstate/Pulumi state that can contain secrets. Never commit it
  (already in `.gitignore`, along with `.terraform/` and `*.tfstate*`). Never put real credentials in
  specs, fixtures or examples.
- Bare `iacforge` output is human text; use `--json` (or `IACFORGE_OUTPUT=json`) when parsing.
- `plan`/`apply` JSON includes a long `log` field; don't paste it wholesale into prompts.

## Where new code goes

- New provider: `adapters/<name>.py` (subclass `ProviderAdapter`, export `ADAPTER` + `EXAMPLES`),
  register in `ADAPTER_MODULES`, add `tests/test_adapter_<name>.py`. Contract tests run automatically.
- New operation: function in `core.py`, row in `surfaces.py`, CLI subparser + `dispatch`, MCP tool in
  `TOOLS`. Parity test must pass.
- New error: subclass in `errors.py` with unique `code`/`exit_code`; document it in
  `docs/agents/using-iacforge.md`.
- Spec model changes: `spec.py`, then `python scripts/gen_schema.py` and commit the schema.
- Engine behaviour: `engines/`. Never in adapters or surfaces.

## Before you commit

1. `ruff check .` clean.
2. `pytest -q -m "not tofu"` green (run full `pytest -q` if you touched engines/adapters and have network).
3. Schema file regenerated if spec/adapters changed (`tests/test_schema_file.py` checks it).
4. Docs updated where commands, error codes, providers or tool names changed
   (README, `docs/agents/using-iacforge.md`, this file).
5. No `.iacforge/`, tfstate, `out/` or credentials staged.
