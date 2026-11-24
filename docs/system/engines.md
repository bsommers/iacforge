# Engines

Engines turn a `BoundStack` into real infrastructure and own every subprocess and every byte of
state. Two implementations exist: `TerraformEngine` (`engines/terraform.py`, serves both `opentofu`
and `terraform`) and `PulumiEngine` (`engines/pulumi.py`). The contract is in
[contracts.md](contracts.md#engine).

## Workdir

`core.resolve_workdir` picks `--workdir` if given, otherwise `<spec dir>/.iacforge/<stack>/<engine>`
(the current directory when the spec is inline text or stdin). Everything the engine produces
(rendered files, plugin cache, lock file, state) lives there. `.iacforge/`, `.terraform/`,
`*.tfstate*` and `.terraform.lock.hcl` are in `.gitignore`.

## TerraformEngine

### Binary selection

`IACFORGE_TF_BINARY` (a name or path) wins outright. Otherwise flavor `opentofu` tries `tofu` then
`terraform`; flavor `terraform` tries `terraform` then `tofu` ([ADR 0002](../adr/0002-opentofu-default.md)).
If nothing is found, `ToolMissingError` with an install hint. Resolution goes through the injected
`which`.

### Environment and flags

Every command gets `TF_IN_AUTOMATION=1`, `TF_INPUT=0`, `CHECKPOINT_DISABLE=1`, and the flags
`-input=false -no-color`. Timeout is 3600 s per command. Non-zero exits (other than the allowed
codes) become `EngineError` carrying the command, exit code and the last 40 lines of stderr and last
10 of stdout.

### Command sequences

All operations first `render()` (write `main.tf.json`) and then `init` (see caching below).

| Operation | Commands |
|---|---|
| `render` | none; writes `main.tf.json` only |
| `plan` | `init` (cached), `plan -out=tfplan -detailed-exitcode` (exit 0 or 2 accepted), `show -json tfplan` |
| `apply` | `init` (cached), `apply -auto-approve`, `output -json` |
| `destroy` | `init` (cached), `destroy -auto-approve` |
| `outputs` | `init` (cached; renders first only if `main.tf.json` is missing), `output -json` |
| `tool_status` | `<binary> version -json` (reads `terraform_version`) |

`-auto-approve` is safe because the confirm gate has already been passed in `core`.

### Init caching

`_init` computes the SHA-256 of `main.tf.json` and compares it to
`.terraform/iacforge-init.sha256`. `init` is skipped only when that stamp matches **and**
`.terraform.lock.hcl` exists. Otherwise it runs `init` and rewrites the stamp. Consequence: editing
the spec (which changes `main.tf.json`) re-inits; an unchanged re-plan is fast and works offline.
There is no `-upgrade`; delete the workdir lock file to force provider upgrades.

### Plan parsing

`show -json` output is parsed and `resource_changes[]` counted by `change.actions`:

- `["no-op"]`, `["read"]` or empty: ignored.
- contains `create` -> `add`; `update` -> `change`; `delete` -> `destroy` (so a replacement,
  `["delete","create"]`, counts as one add and one destroy).

The result is `{"changes": {add, change, destroy}, "resources": [{address, actions}], "has_changes":
returncode == 2, "log": ...}`. A JSON parse failure is an `EngineError`.

### Apply/destroy summaries and outputs

`apply`/`destroy` parse `Resources: N added, N changed, N destroyed` (or `Destroy complete! Resources:
N destroyed`) from stdout; zeros if absent. Outputs come from `output -json`: each flat
`<tf_id>__<key>` is nested by `nest_outputs` and the `tf_id` is mapped back to the original stack
resource name.

## PulumiEngine

### Prerequisites

Pulumi CLI on `PATH` (`ToolMissingError` otherwise) and the Python SDK (`pip install
'iacforge[pulumi]'`, plus the provider extra such as `pulumi-docker`, `pulumi-gcp`; see
`pulumi_packages`). Both are checked at stack-open time and via `tool_status()`.

### Automation API

`_open_stack` creates the workdir `state/` directory, builds `ProjectSettings(name="iacforge",
runtime="python", backend=file://<workdir>/state)` and calls
`create_or_select_stack(stack_name=<stack name>, project_name="iacforge", program=lambda:
run_pulumi_program(b), opts=LocalWorkspaceOptions(work_dir=workdir, env_vars=...))`. The program is
run **in-process** with cwd switched to the workdir (so relative paths such as the `local` provider's
`out/hello.txt` resolve there).

| Operation | Automation call | Result mapping |
|---|---|---|
| `plan` | `stack.preview()` | `change_summary` -> counts; `resources` is `[]`; `has_changes = any(counts)` |
| `apply` | `stack.up()` | `summary.resource_changes`, `outputs` (values unwrapped) |
| `destroy` | `stack.destroy()` | `summary.resource_changes` |
| `outputs` | `stack.outputs()` | nested outputs |

Summary mapping (`_summary_to_changes`): `add = create + replace`, `change = update`, `destroy =
delete + replace`. Any exception from the SDK is wrapped as `EngineError("pulumi failed: <type>")`
with the last 40 lines of stderr. `_open_stack` is a deliberate seam: tests replace it with a
fake stack (`tests/test_engine_pulumi.py`).

### Backend and secrets

The backend is always a local file backend at `<workdir>/state` (no Pulumi Cloud account). Env set
for every call: `PULUMI_BACKEND_URL`, `PULUMI_CONFIG_PASSPHRASE` (from the environment, else the
empty string), `PULUMI_SKIP_UPDATE_CHECK`, `PULUMI_AUTOMATION_API_SKIP_VERSION_CHECK`. Set a real
`PULUMI_CONFIG_PASSPHRASE` when a stack holds secrets. See [security](security.md).

### Ejected project

`render()` writes a standalone project that works without the iacforge engine:

| File | Content |
|---|---|
| `Pulumi.yaml` | `name: iacforge`, `runtime: python`, `backend.url: file://./state` |
| `stack.json` | the validated spec (`model_dump(by_alias=True, mode="json")`, sorted keys) |
| `__main__.py` | loads `stack.json`, calls `run_pulumi_program(bind(parse_spec(...), "pulumi"))` |
| `requirements.txt` | `iacforge`, `pulumi>=3.100`, plus the adapter's `pulumi_packages` |

`cd <workdir> && pulumi up` then runs the same program. Note that the ejected program still imports
`iacforge` (it is a thin loader, not a standalone translation).

## Adding an engine

1. Subclass `Engine` in `engines/<name>.py`; implement `tool_status`, `render`, `plan`, `apply`,
   `destroy`, `outputs` with the documented result shapes.
2. Route every process through `self.runner`, every binary lookup through `self.which`.
3. Register in `engines/__init__.py` (`ENGINE_NAMES`, `get_engine`) and add the name to
   `spec.ENGINES` / the `Literal` in `StackBody.engine`, `render.ENGINE_FAMILY`, the CLI `choices`,
   and an engine family constant in `adapters/base.py` plus each adapter's `engines`.
4. Add an ADR (this extends the contract), a fake-runner test file modelled on
   `tests/test_engine_terraform.py`, and a CI job step.
