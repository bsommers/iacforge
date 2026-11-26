# Using iacforge as an AI agent or program

For agents and code that *provision* infrastructure with iacforge. (To modify iacforge itself, see
`/AGENTS.md`.) All examples below are captured from real runs with the `local` provider and OpenTofu.

## Recommended loop

1. `providers` - list providers, resource types, status (`stable`/`beta`/`scaffold`), platforms.
2. `doctor` - confirm the chosen provider is `ready` on this host (engine binary, docker, ...).
3. `schema <provider>` - exact property names/types for that provider. Whole-stack schema:
   `schema` (also committed at `docs/agents/spec.schema.json`).
4. Write the spec (YAML or JSON) - never invent property names; unknown keys are errors.
5. `validate` - fast, touches nothing. Fix errors using `details` (see below).
6. `plan` - read `changes` and per-resource `actions`. Show the human anything that is not a pure create.
7. `apply` with confirmation - only after plan review and, for real infrastructure, human approval.
8. `outputs` - read results (ids, addresses) as `{resource: {key: value}}`.
9. `destroy` with confirmation - only on explicit human intent.

To adopt an existing resource: declare it in the spec, `validate`/`plan`, then `import --resource NAME [--id ID]` with confirmation (human approval; writes state). Read the returned plan before any `apply`.

CLI: `iacforge --json <command> [spec.yaml] [--engine E] [--workdir DIR] [--yes]`. Spec may be `-`
for stdin. Without `--json` output is human text (set `IACFORGE_OUTPUT=json` to force JSON).

## Minimal spec

```yaml
apiVersion: iacforge/v1
kind: Stack
metadata: {name: dev}          # ^[a-z][a-z0-9-]{0,62}$ ; also the state key
spec:
  provider: local
  engine: opentofu             # opentofu | terraform | pulumi
  providerConfig: {}
  resources:
    - name: hello
      type: file
      properties: {path: out/hello.txt, content: "hello from iacforge\n"}
```

Other resources are referenced through provider-specific explicit fields (for example a `*Ref`
property naming another resource); `dependsOn: [name]` adds ordering. `iacforge schema <provider>`
documents them. Relative local paths resolve against the workdir
(`<spec dir>/.iacforge/<stack>/<engine>`), not your cwd.

## JSON envelope

Every surface (CLI `--json`, MCP tools) returns one envelope:

```json
{"ok": true,  "command": "validate", "data": { ... }}
{"ok": false, "command": "validate", "error": {"code": "...", "message": "...", "details": ...}}
```

Branch on `ok` then `error.code` (stable); never parse `message`. `details` is optional.

Captured examples (keys sorted; `log` truncated):

```json
// validate
{"command":"validate","data":{"engine":"opentofu","provider":"local","resources":["hello"],"stack":"dev","valid":true},"ok":true}

// plan  (read changes + resources[].actions; log is raw engine output, long)
{"command":"plan","data":{"changes":{"add":1,"change":0,"destroy":0},"engine":"opentofu","has_changes":true,
 "log":"...","provider":"local","resources":[{"actions":["create"],"address":"local_file.hello"}],
 "stack":"dev","workdir":"/work/.iacforge/dev/opentofu"},"ok":true}

// apply --yes  (outputs nested by resource name)
{"command":"apply","data":{"changes":{"add":1,"change":0,"destroy":0},"engine":"opentofu","log":"...",
 "outputs":{"hello":{"id":"2c1a559b8b8f5549590d6e8434bc61148f73b080","path":"out/hello.txt"}},
 "provider":"local","resources":["hello"],"stack":"dev","workdir":"/work/.iacforge/dev/opentofu"},"ok":true}

// render  (writes files only; runs no engine)
{"command":"render","data":{"engine":"opentofu","files":["main.tf.json"],"provider":"local",
 "resources":["hello"],"stack":"dev","workdir":"/work/.iacforge/dev/opentofu"},"ok":true}

// providers local
{"command":"providers","data":{"providers":[{"category":"local","description":"Files on the local filesystem ...",
 "docs_url":"https://registry.terraform.io/providers/hashicorp/local/latest/docs",
 "engines":["opentofu","terraform","pulumi"],"name":"local","platforms":["darwin","linux","windows"],
 "pulumi_packages":["pulumi"],"required_tools":[],"resource_types":["file"],"status":"stable"}]},"ok":true}

// doctor (abridged): per-provider readiness
{"command":"doctor","data":{"engines":{"opentofu":true,"pulumi":false,"terraform":true},"platform":"linux",
 "providers":[{"missing_tools":["multipass"],"name":"multipass","platform_supported":true,"ready":false,"status":"beta"}, ...],
 "pulumi_sdk_installed":true,"tools":{"tofu":"/snap/bin/tofu","pulumi":null, ...}},"ok":true}
```

`warnings` (list of strings) may appear in `data`, e.g. provider not supported on this host OS:
render works, apply will likely fail.

## Error codes

| code | exit | meaning | self-correction |
|---|---|---|---|
| `invalid_spec` | 2 | spec unreadable or fails validation | read `details` (below), fix, re-validate |
| `unknown_provider` | 2 | provider name not registered | `details.known` lists valid names |
| `unsupported` | 2 | resource type, engine or host OS not supported by provider | check `providers <name>` (`resource_types`, `engines`, `platforms`) |
| `tool_missing` | 3 | tofu/terraform/pulumi/docker/... absent | `details.hint`; run `doctor`; ask human to install, or switch `--engine` |
| `engine_failed` | 4 | engine ran and failed | read `details` (stdout/stderr tail); fix spec or environment; do not blindly retry apply |
| `not_confirmed` | 5 | apply/destroy without confirmation | review plan, obtain approval, then confirm |
| `internal` | 1 | unexpected bug (code `error` for typed generic) | report; do not loop |

Other exit: 0 ok. Real examples:

```json
{"command":"validate","error":{"code":"invalid_spec","message":"spec failed provider validation","details":[
  {"message":"Field required","path":"spec.resources[0].properties.path"},
  {"message":"Extra inputs are not permitted","path":"spec.resources[0].properties.pth"}]},"ok":false}

{"command":"validate","error":{"code":"unknown_provider","message":"unknown provider 'nope'",
 "details":{"known":["aws","docker","gcp","hyperv","libvirt","local","multipass"]}},"ok":false}

{"command":"apply","error":{"code":"not_confirmed","message":"'apply' changes real infrastructure; re-run with confirmation (CLI: --yes, Python: confirm=True, MCP: confirm=true)",
 "details":{"provider":"local","stack":"dev"}},"ok":false}

{"command":"plan","error":{"code":"tool_missing","message":"pulumi CLI not found",
 "details":{"hint":"install the Pulumi CLI (https://www.pulumi.com/docs/install/) and `pip install 'iacforge[pulumi]'`"}},"ok":false}
```

Reading `invalid_spec.details`: a list of `{path, message}`. `path` is a dotted location in the
document (`spec.resources[0].properties.pth`). "Field required" at `...properties.path` plus
"Extra inputs are not permitted" at `...properties.pth` means a misspelled key: rename `pth` to `path`.
Other details paths may be `resources.<name>` (e.g. "references unknown resource(s): x" - fix the
reference or add the resource). Resource index and name come from your own spec, so edit exactly
that node; then re-run `validate` until `ok` is true.

## MCP setup

Install: `pip install 'iacforge[mcp]'` (provides `iacforge-mcp`, stdio transport).

Claude Code:

```bash
claude mcp add iacforge -- iacforge-mcp
```

Other clients (Claude Desktop, Cursor, etc.) JSON config:

```json
{"mcpServers": {"iacforge": {"command": "iacforge-mcp", "args": []}}}
```

If installed in a venv use its absolute path, e.g. `/path/to/.venv/bin/iacforge-mcp`.
Tools (one per operation): `iacforge_version`, `iacforge_providers`, `iacforge_schema`,
`iacforge_doctor`, `iacforge_validate`, `iacforge_render`, `iacforge_plan`, `iacforge_outputs`,
`iacforge_apply`, `iacforge_destroy`, `iacforge_import`. `spec` is a file path or inline YAML/JSON text; apply/destroy/import
take `confirm=true`. There is no `init` tool: write the spec directly from `iacforge_schema`.
Note: file paths and workdir are resolved on the MCP server's host and cwd.

## Python API

```python
from iacforge import core
from iacforge.errors import IacForgeError, NotConfirmedError

spec = {
    "apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "dev"},
    "spec": {"provider": "local", "resources": [
        {"name": "hello", "type": "file", "properties": {"path": "out/hello.txt", "content": "hi\n"}}]},
}
try:
    core.validate(spec)                      # dict, StackSpec, Path, file-path str, or inline YAML str
    p = core.plan(spec, workdir="/datanapps/claude-tmp/work")
    assert p["changes"]["destroy"] == 0      # review gate (yours)
    core.apply(spec, workdir="/datanapps/claude-tmp/work", confirm=True)   # only after approval
    print(core.outputs(spec, workdir="/datanapps/claude-tmp/work")["outputs"])
except IacForgeError as e:
    print(e.code, e.exit_code, e.message, e.details)   # same codes as the CLI/MCP
```

Functions return plain dicts (the envelope's `data`) and raise `IacForgeError` subclasses.
Without `confirm=True`, `apply`/`destroy` raise `NotConfirmedError`.

## Safety rules for agents

- Never `apply` without having run `validate` and `plan` and reviewed the plan. Treat any
  `change` or `destroy` count > 0 on an existing stack as needing human sign-off.
- Never pass `confirm=true` / `--yes` on your own initiative for real (non-scratch) infrastructure;
  get explicit human approval first. `destroy` requires explicit human intent naming the stack.
- Never put credentials, tokens or private keys in specs, `providerConfig` or `properties`. Use the
  provider's ambient mechanism (environment variables, credential files, cloud ADC) instead.
- `<spec dir>/.iacforge/` holds engine state, which may contain secrets: don't read it into
  prompts, print it, or commit it. `plan`/`apply` `log` may also echo values.
- Prefer a scratch `--workdir` and the `local` provider to rehearse; use `render` to inspect output.
- Don't retry a failed `apply` in a loop; read the error, fix the cause, re-plan.
- Don't hand-edit rendered files or state; change the spec and re-run.
