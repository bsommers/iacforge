# Security

iacforge drives tools that create and destroy real infrastructure, and is explicitly meant to be
called by AI agents. This page lists what it protects, what it does not, and where to look.

## Assets and trust boundaries

| Asset | Where it lives |
|---|---|
| Cloud/host credentials | the ambient environment (ADC, AWS profile, Docker socket), never the spec |
| Infrastructure | whatever the provider's API reaches |
| State (may contain secrets) | the workdir: `terraform.tfstate`, Pulumi `state/` |
| The spec | a file or inline text supplied by a human or an agent: **untrusted input** |

Trust boundaries: (1) spec text -> `core` (validated before use); (2) iacforge -> engine binaries
(argument lists, fixed commands); (3) MCP client -> iacforge process (runs with the user's
privileges).

## Controls

### No credentials in the spec
Provider config models carry only identifiers (`project`, `region`, `zone`, `profile`, docker
`host`). The GCP adapter documents ADC / workload identity; AWS uses the standard credential chain
with an optional `profile` name. There is no field for keys or tokens, and models reject unknown
keys (`extra="forbid"`), so a stray `credentials:` is a validation error rather than a silent
leak into `main.tf.json`. The docker adapter's `RegistryAuth` (`adapters/docker.py`) deliberately
accepts only `address` and `configFile`: registry credentials come from a docker `config.json`
populated by `docker login`, never from the spec (a test enforces that `password` is rejected).

### Subprocess execution without a shell
All process execution is in `engines/base.subprocess_runner`: `subprocess.run(list, ...)`, no
`shell=True`. Spec values reach engines only as data inside `main.tf.json` (serialised by
`json.dumps`, no string templating of HCL) or as Pulumi resource arguments, never as command
arguments. The command lines are fixed in the engines. The resolved binary can be redirected with
`IACFORGE_TF_BINARY`, so treat that variable as trusted-environment only.

### Confirm gate
`apply` and `destroy` raise `NotConfirmedError` (exit 5, code `not_confirmed`) unless `confirm=True`;
the gate is in `core._gate`, so the CLI (`--yes`; interactive prompt only on a TTY and never with
`--json`), the Python API and MCP (`confirm: true`) cannot skip it. MCP tool docstrings instruct
agents to run `iacforge_validate` and `iacforge_plan` first. The gate is a speed bump and an audit
point, not authorization: anything that can call `confirm=true` can change infrastructure.
`plan`, `validate`, `render` and `outputs` do not need confirmation (they do run `init`, which can
download providers; `plan` also contacts provider APIs).

### State files contain secrets
Terraform state and Pulumi file-backend state include resource attributes in clear text (generated
passwords, private keys, connection strings). Defaults:

- state is local to the workdir `.iacforge/<stack>/<engine>/`; `.gitignore` excludes `.iacforge/`,
  `.terraform/`, `*.tfstate`, `*.tfstate.*`, `.terraform.lock.hcl`, `out/`;
- Pulumi's passphrase defaults to the empty string unless `PULUMI_CONFIG_PASSPHRASE` is set, so
  its secret encryption is nominal for dev. Set a real passphrase for stacks with secrets;
- in your own repos, never commit `.iacforge/`; for shared stacks use remote state with access
  control (planned: GCS, see [gcp-plan.md](gcp-plan.md)).

The ejected Pulumi project (`render`) contains `stack.json`, a copy of the spec; it holds no
credentials but may hold sensitive property values (startup scripts, metadata).

### MCP exposure
`iacforge-mcp` is a stdio server that runs with the privileges of whoever launched it. Its tools
accept `spec` as **a filesystem path or inline text**, so a client can make the server read any
file the user can read (parse errors may echo content in messages) and `workdir` can point
state/rendering anywhere writable. Mitigations: run it only for clients you trust, in a dedicated
low-privilege account or container with scoped cloud credentials, and use plan-only credentials
for review sessions. `init` is deliberately not exposed over MCP (it writes into the server's
cwd). Do not expose the server over a network transport without adding authentication; only
stdio is supported.

### Spec as hostile input
Specs are parsed with `yaml.safe_load` (no object construction). Names are constrained by
`^[a-z][a-z0-9-]{0,62}$` so they are safe as Terraform identifiers and resource names. Providers
that accept free-form strings (`startupScript`, container `command`) pass them as data to the
provider, where they execute on the target machine by design: review specs from untrusted
sources like code.

### Supply chain
- **CI actions** are pinned to full commit SHAs with the version in a trailing comment
  (`actions/checkout`, `astral-sh/setup-uv`, `opentofu/setup-opentofu`), `permissions: contents: read`,
  `persist-credentials: false` on checkout, `timeout-minutes: 30`.
- **Providers**: adapters pin Terraform providers with pessimistic constraints (e.g. `~> 6.0`),
  and `.terraform.lock.hcl` records hashes after first `init`; commit it in your own infra repo to
  freeze provider versions.
- **Python deps** are lower-bounded in `pyproject.toml` (`pydantic>=2.7`, `pyyaml>=6.0`); heavy SDKs
  (`pulumi`, provider packages, `mcp`) are optional extras so the default install stays small.
- iacforge never downloads engines; the install scripts only install the Python package through
  `uv`/`pipx` and tell the user to install OpenTofu/Pulumi themselves.

## Known gaps and hardening ideas

- Pulumi empty-passphrase default (above).
- `doctor` and `plan` run before any policy check; policy hooks (deny public buckets, required
  labels) are roadmapped for v0.3.
- No spec size limits; a huge inline spec over MCP is processed in memory.
- No audit log of applies beyond the engine logs in the returned envelope.
- Python dependencies are not hash-pinned (no lock file is committed); `uv.lock` in CI would
  improve reproducibility.
