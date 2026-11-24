# Testing

```bash
uv sync --extra dev --extra mcp     # CI also uses these extras
uv run ruff check .                 # lint gate
uv run pytest -q                    # test gate
```

## Layout

| File | Covers |
|---|---|
| `tests/conftest.py` | `tf_binary()` helper, `tf_bin` and `pulumi_bin` fixtures (skip when the tool is absent) |
| `tests/test_adapter_contract.py` | shared contract suite, parametrised over every registered adapter |
| `tests/test_adapter_<name>.py` | per-provider: `docker`, `libvirt`, `hyperv`, `multipass`, `gcp`, `aws` rendering, validation, negative cases, Pulumi mocks |
| `tests/test_engine_terraform.py` | `TerraformEngine` against a fake `Runner` (+ one real tofu test) |
| `tests/test_engine_pulumi.py` | `PulumiEngine` with a fake stack (+ one real pulumi test) |
| `tests/test_core_cli.py` | CLI envelope, exit codes, gating, `init`, human output |
| `tests/test_mcp_server.py` | MCP tool envelopes, confirm requirement, tool docstrings warn agents |
| `tests/test_surface_parity.py` | every core op appears in `surfaces.OPERATIONS`, CLI and MCP; exclusions documented |

## Markers

Declared in `pyproject.toml`:

| Marker | Needs |
|---|---|
| `tofu` | `tofu` or `terraform` binary and network access to download providers |
| `pulumi` | the `pulumi` CLI |
| `docker` | a running Docker daemon |

Tests that need a missing tool skip themselves (`tf_bin` / `pulumi_bin` fixtures, or an inline
`pytest.skip`; the contract suite also skips if provider download fails offline). Markers are for
selection, not for gating skips.

## Running subsets

```bash
uv run pytest -q -m "not tofu"                    # no OpenTofu needed (what CI runs on macOS/Windows)
uv run pytest -q -m "not tofu and not docker and not pulumi"   # pure unit tests, fully offline
uv run pytest -q -m tofu                          # real tofu validate/apply tests only
uv run pytest -q -m docker                        # live docker apply (needs daemon and tofu)
uv run pytest -q tests/test_adapter_contract.py   # contract suite for all providers
uv run pytest -q tests/test_adapter_gcp.py -k deterministic
```

## Seams: fakes instead of binaries

- **Runner seam.** `core.plan/apply/destroy/outputs/render` accept `runner=`; engines take it in the
  constructor. The Terraform test `Fake` records `(args, cwd, env)` and returns canned `ProcResult`s
  keyed by the sub-command (`init`, `plan`, `show`, `apply`, `output`). Assert on `fake.verbs` to
  verify command sequences and init caching.
- **Which seam.** Engines accept `which=` so binary selection is tested without installing anything.
- **Pulumi seam.** `PulumiEngine._open_stack` is replaced with a fake stack object (`preview`, `up`,
  `destroy`, `outputs`), so no CLI is needed. Adapter-level Pulumi programs are checked with Pulumi
  mocks (e.g. `test_pulumi_program_with_mocks` in `tests/test_adapter_docker.py`).
- **`doctor(which=...)`** takes an injectable `which` for the same reason.

## Contract suite and EXAMPLES

Every adapter's `EXAMPLES` feed `tests/test_adapter_contract.py`. A new provider that registers
without `EXAMPLES` covering all its resource types fails immediately. See
[contracts.md](contracts.md#examples-requirement).

## CI

`.github/workflows/ci.yml` runs on push to `main` and every pull request, with `permissions:
contents: read` and cancel-in-progress concurrency.

| Dimension | Values |
|---|---|
| OS | ubuntu-latest, macos-latest, windows-latest |
| Python | 3.11, 3.13 (the package supports `>=3.10`) |

Steps: checkout (no persisted credentials) -> `setup-uv` -> `setup-opentofu` (`tofu_wrapper:
false`) -> `uv sync --extra dev --extra mcp` -> `uv run ruff check .` -> tests. On Linux the full
suite runs (including `tofu` tests); on macOS/Windows `pytest -q -m "not tofu"`. The Pulumi live test skips in CI (no Pulumi CLI is installed). The Docker live test
(`test_live_apply_alpine`) runs on Linux runners because GitHub's ubuntu images ship a Docker daemon,
and skips elsewhere. All actions are pinned by commit SHA; see [security](security.md).

## Writing tests

- Prefer asserting on rendered dicts (`render_terraform(bind(parse_spec(doc), "opentofu"))`) over
  string matching.
- Deep-copy `EXAMPLES` before mutating (adapters must not mutate their input;
  `test_example_not_mutated_by_render`).
- Add negative tests for each validator and for wrong-type references.
- Live tests get the right marker(s) and must clean up (`destroy`) in a `finally`.
