# CLI reference

```
iacforge [-h] [--json] COMMAND ...
```

Entry points: `iacforge` (CLI) and `iacforge-mcp` (MCP server, see [MCP](mcp.md)). `python -m iacforge.cli` also works.

## Global options

| Option | Description |
|---|---|
| `-h`, `--help` | Show help (also valid after any command). |
| `--json` | Print one JSON envelope on stdout instead of human text. Accepted before or after the command: `iacforge --json plan` and `iacforge plan --json` are equivalent. |

Environment: `IACFORGE_OUTPUT=json` has the same effect as `--json` for any command. `IACFORGE_TF_BINARY` selects the OpenTofu/Terraform binary ([Engines](engines.md)). `PULUMI_CONFIG_PASSPHRASE` is used by the Pulumi engine.

## Commands

| Command | Changes infrastructure | Description |
|---|---|---|
| `version` | no | Print iacforge version, engine names and provider names. |
| `providers [NAME]` | no | List providers with status, platforms, engines, resource types, required tools. |
| `schema [PROVIDER]` | no | Print the JSON Schema of the stack document, or of one provider's `providerConfig` and resource properties. Output is JSON in both modes. |
| `doctor` | no | Report host tools, engines and per-provider readiness. |
| `init` | writes a file | Write a starter `stack.yaml`. |
| `validate [SPEC]` | no | Validate a spec against its provider. |
| `render [SPEC]` | writes workdir | Write engine-native files (`main.tf.json` or a Pulumi project) without running the engine. |
| `plan [SPEC]` | no | Show what `apply` would change. |
| `outputs [SPEC]` | no | Show outputs of an applied stack. |
| `apply [SPEC]` | **yes** | Create or update infrastructure. |
| `destroy [SPEC]` | **yes** | Delete all of the stack's infrastructure. |
| `import [SPEC] --resource NAME [--id ID]` | **yes** | Adopt an existing resource (declared in the spec) into state, then plan. |

### Spec commands: `validate`, `render`, `plan`, `outputs`, `apply`, `destroy`

```
iacforge [--json] COMMAND [--engine {opentofu,terraform,pulumi}] [--workdir WORKDIR] [-y] [SPEC]
```

| Argument | Default | Description |
|---|---|---|
| `SPEC` | `stack.yaml` | Spec file (YAML or JSON), or `-` to read the spec from stdin. |
| `--engine` | `spec.engine` | Override the engine for this run. |
| `--workdir DIR` | `<spec dir>/.iacforge/<stack>/<engine>` | State and render directory. |
| `-y`, `--yes` | off | `apply` and `destroy` only. Confirm without prompting. |

Notes:

- `validate` accepts `--workdir` but does not use it.
- `apply`/`destroy` without `--yes`: in a terminal you get a prompt (`Continue? [y/N]`); with `--json` or when stdin is not a TTY, they fail with `not_confirmed` (exit 5) and change nothing.
- `plan` renders, runs `init` (skipped when config and lock file are unchanged) and plans. It does not change infrastructure but does write to the workdir.
- `render` writes only files: nothing is initialised or run.

### `import`

```
iacforge import [SPEC] --resource NAME [--id ID] [-y] [--engine E] [--workdir DIR]
```

Writes state, so it is gated like `apply` (`not_confirmed`, exit 5, without `--yes`). `--id` is the provider's import ID; when omitted the provider derives it (gcp does; others fail with `unsupported` unless you pass `--id`). The JSON data is the `plan` envelope plus `imported` `{resource, address, id}`. Pulumi import needs the provider to define a Pulumi type token.

### `init`

```
iacforge init [--provider PROVIDER] [--name NAME] [--engine {opentofu,terraform,pulumi}] [--path PATH] [--force]
```

| Option | Default | Description |
|---|---|---|
| `--provider` | `local` | Provider to scaffold for. `local` and `docker` get a working starter; any other provider gets an empty resource list. |
| `--name` | `dev` | Stack name (`metadata.name`). |
| `--engine` | `opentofu` | Engine written to the spec. |
| `--path` | `stack.yaml` | File to write; parent directories are created. |
| `--force` | off | Overwrite an existing file (otherwise `invalid_spec`, exit 2). |

### `providers`, `schema`

`iacforge providers` prints one block per provider:

```
local      stable    local  platforms=darwin,linux,windows engines=opentofu,terraform,pulumi
           types: file
```

`iacforge providers docker` shows one. `iacforge schema` with no argument prints the stack schema; `iacforge schema gcp` prints `{"provider", "providerConfig", "resources": {<type>: <schema>}}`.

## JSON envelope

With `--json` every command prints exactly one JSON object (keys sorted) on stdout and sets the exit code.

Success:

```json
{"ok": true, "command": "validate", "data": {"engine": "opentofu", "provider": "local", "resources": ["hello"], "stack": "dev", "valid": true}}
```

Failure:

```json
{"ok": false, "command": "validate", "error": {"code": "invalid_spec", "message": "spec failed validation", "details": [{"path": "metadata.name", "message": "String should match pattern '^[a-z][a-z0-9-]{0,62}$'"}]}}
```

`error.details` is optional. Branch on `error.code` (stable), never on `message`.

### `data` by command

| Command | Keys in `data` |
|---|---|
| `version` | `version`, `engines`, `providers` |
| `providers` | `providers`: list of `{name, description, status, category, platforms, engines, resource_types, required_tools, pulumi_packages, docs_url}` |
| `schema` | `schema` |
| `doctor` | `platform`, `tools` (path or `null` per tool), `engines` (`opentofu`/`terraform`/`pulumi` booleans), `pulumi_sdk_installed`, `providers` (`name`, `status`, `platform_supported`, `missing_tools`, `ready`, `ready_engines`: list of engines usable for that provider on this host) |
| `init` | `path`, `document` |
| `validate` | `stack`, `provider`, `engine`, `resources` (names in dependency order), `valid`; `warnings` if any |
| `render` | the base keys above + `workdir`, `files` |
| `plan` | base keys + `workdir`, `changes` `{add, change, destroy}`, `resources` (`[{address, actions}]`; empty under Pulumi), `has_changes`, `log` |
| `apply` | base keys + `workdir`, `changes`, `outputs` `{resource: {key: value}}`, `log` |
| `destroy` | base keys + `workdir`, `changes`, `log` |
| `outputs` | base keys + `workdir`, `outputs` |
| `import` | `plan` keys + `imported` `{resource, address, id}` |

The base keys are `stack`, `provider`, `engine`, `resources` (and `warnings` when present).

Human output prints a one-line summary instead, plus `warning: ...` lines.

## Exit codes

| Code | Meaning | `error.code` |
|---|---|---|
| 0 | Success | - |
| 1 | Unexpected internal error | `internal` or `error` |
| 2 | Bad usage or invalid spec (also unknown provider, unsupported engine/resource, unreadable spec file, `init` refusing to overwrite) | `invalid_spec`, `unknown_provider`, `unsupported` |
| 3 | A required tool is missing (tofu/terraform, pulumi, Pulumi SDK) | `tool_missing` |
| 4 | The engine ran and failed (provider error, apply failure). `details` carries the command, exit code and the tail of stderr/stdout. | `engine_failed` |
| 5 | `apply`/`destroy`/`import` without confirmation | `not_confirmed` |

argparse usage errors (unknown command or flag) print usage to stderr and exit 2. Ctrl-C exits 2.

## Examples

```sh
iacforge validate examples/docker/stack.yaml
iacforge plan --engine terraform
iacforge --json apply --yes | jq '.data.outputs'
cat stack.yaml | iacforge validate -
iacforge render --workdir ./eject            # inspect or hand-run the generated config
iacforge doctor && iacforge --json providers gcp
```
