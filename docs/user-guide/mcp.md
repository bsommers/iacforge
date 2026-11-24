# MCP server

`iacforge-mcp` exposes iacforge to MCP clients (Claude Code, Claude Desktop, and others) over stdio. It is a thin adapter over the same core as the CLI: one tool per operation, same results, same error codes.

## Install

The server needs the `mcp` extra:

```sh
uv tool install "iacforge[mcp] @ git+https://github.com/bsommers/iacforge"
iacforge-mcp    # starts the stdio server and waits for a client; Ctrl-C to stop
```

`scripts/install.sh` and `scripts/install.ps1` already include the extra. Without it, `iacforge-mcp` prints `the 'mcp' package is required ... pip install 'iacforge[mcp]'` and exits with code 3.

The engines and provider tools you need ([Installation](installation.md)) must be available to the **MCP client's** environment, not just your interactive shell. If the client does not inherit your `PATH`, use absolute paths or set `env` in its config.

## Configure a client

### Claude Code

```sh
claude mcp add iacforge -- iacforge-mcp                 # this project, local scope
claude mcp add --scope user iacforge -- iacforge-mcp    # all projects
claude mcp list
```

Or commit a project-level `.mcp.json`:

```json
{
  "mcpServers": {
    "iacforge": { "command": "iacforge-mcp", "args": [] }
  }
}
```

If you run from a clone's virtualenv, use the full path, for example `"command": "/path/to/iacforge/.venv/bin/iacforge-mcp"`.

### Claude Desktop

Edit `claude_desktop_config.json` (Settings > Developer > Edit Config) and restart the app:

```json
{
  "mcpServers": {
    "iacforge": {
      "command": "iacforge-mcp",
      "env": { "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/adc.json" }
    }
  }
}
```

Desktop apps often have a minimal `PATH`: use the absolute path to `iacforge-mcp` (`which iacforge-mcp`) if it is not found.

### Other clients

Any MCP client that can launch a stdio server: command `iacforge-mcp`, no arguments, transport stdio.

## Tools

| Tool | Parameters | Changes infrastructure |
|---|---|---|
| `iacforge_version` | none | no |
| `iacforge_providers` | `name?` | no |
| `iacforge_schema` | `provider?` | no |
| `iacforge_doctor` | none | no |
| `iacforge_validate` | `spec`, `engine?` | no |
| `iacforge_render` | `spec`, `engine?`, `workdir?` | writes workdir files only |
| `iacforge_plan` | `spec`, `engine?`, `workdir?` | no |
| `iacforge_outputs` | `spec`, `engine?`, `workdir?` | no |
| `iacforge_apply` | `spec`, `engine?`, `workdir?`, `confirm` | **yes** |
| `iacforge_destroy` | `spec`, `engine?`, `workdir?`, `confirm` | **yes** |

- `spec` is a **path** to a spec file or the **inline YAML/JSON text** itself. Inline text without a file uses the server's current directory as the workdir base (set `workdir` to control it).
- `engine` is `opentofu`, `terraform` or `pulumi`. Omit to use the spec's own.
- `iacforge init` has no MCP tool on purpose: agents write specs directly, guided by `iacforge_schema`.

Every tool returns the CLI's `--json` envelope as a structured result:

```json
{"ok": true, "command": "plan", "data": {"changes": {"add": 1, "change": 0, "destroy": 0}, "...": "..."}}
{"ok": false, "command": "apply", "error": {"code": "not_confirmed", "message": "..."}}
```

Failures are returned as `ok: false` with an `error.code` (`invalid_spec`, `unknown_provider`, `unsupported`, `tool_missing`, `engine_failed`, `not_confirmed`, `internal`), not as protocol errors. See [CLI reference](cli-reference.md#exit-codes) for the meanings.

## Confirm gating

`iacforge_apply` and `iacforge_destroy` default to `confirm: false`. In that state they validate the spec and then return `not_confirmed` without changing anything. The tool descriptions tell the model to run `iacforge_validate` and `iacforge_plan` first and review the plan before passing `confirm: true`.

Recommended client setup: keep `iacforge_apply` and `iacforge_destroy` on "ask every time" in your client's tool permissions, and allow the read-only tools. `confirm` is a safety interlock in the server, not a substitute for human approval of destructive calls.

## Typical agent flow

1. `iacforge_doctor`: is the engine installed, is the provider ready on this host?
2. `iacforge_providers` and `iacforge_schema` (with a provider name): which resource types and properties exist.
3. Write `stack.yaml`, then `iacforge_validate`.
4. `iacforge_plan`, review the `changes` and `resources`.
5. With human approval, `iacforge_apply` with `confirm: true`; then `iacforge_outputs`.
6. `iacforge_destroy` with `confirm: true` when finished.

For agent-oriented guidance see [docs/agents/using-iacforge.md](../agents/using-iacforge.md) and [AGENTS.md](../../AGENTS.md).
