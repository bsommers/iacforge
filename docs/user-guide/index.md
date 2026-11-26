# iacforge user guide

iacforge turns one provider-neutral YAML stack spec into real infrastructure. It renders the spec to OpenTofu/Terraform JSON or a Pulumi program, runs the engine for you, and exposes the same operations as a CLI, a Python API and an MCP server.

## Start here

1. [Installation](installation.md): iacforge itself, plus the engine and provider tools you need on your OS.
2. [Quickstart](quickstart.md): a working stack in about a minute with the `local` provider, then Docker.
3. [Stack spec reference](stack-spec.md): every field of `stack.yaml`, naming rules, dependencies, workdir and state.

## Reference

- [CLI reference](cli-reference.md): every command, flag, exit code and the `--json` envelope.
- [State backends](state-backends.md): local vs GCS remote state, bootstrapping the bucket.
- [Importing existing resources](import.md): adopt resources into a stack's state.
- [Engines](engines.md): OpenTofu vs Terraform vs Pulumi, binary selection, state, ejecting.
- [MCP server](mcp.md): using iacforge from Claude Code, Claude Desktop and other MCP clients.
- Providers: [local](providers/local.md), [docker](providers/docker.md), [libvirt](providers/libvirt.md), [hyperv](providers/hyperv.md), [multipass](providers/multipass.md), [gcp](providers/gcp.md), [aws](providers/aws.md).

## Help

- [Troubleshooting](troubleshooting.md)
- [FAQ](faq.md)

## Mental model

```
stack.yaml ──validate──> provider adapter (pydantic models) ──render──> main.tf.json   ──> tofu / terraform
 (one spec)                                                          └─> Pulumi program ──> pulumi (Automation API)
```

- The spec says *what* (provider, resources, properties). `spec.engine` says *how* (`opentofu` by default).
- `validate`, `render` and `plan` never change infrastructure. `apply` and `destroy` do, and refuse to run without `--yes` (CLI), `confirm=True` (Python) or `confirm=true` (MCP).
- Everything lives in a per-stack working directory, `.iacforge/<stack>/<engine>/` next to the spec, including state.

## Other documentation

- [Architecture](../architecture.md) and [system docs](../system/contracts.md) for contributors.
- [AGENTS.md](../../AGENTS.md) and [docs/agents/](../agents/using-iacforge.md) if you drive iacforge from an AI agent.
- [Roadmap](../ROADMAP.md) and [ADRs](../adr/).
