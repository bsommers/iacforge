# FAQ

**What is iacforge, in one sentence?**
A provider-neutral way to describe infrastructure in one YAML spec and have it provisioned through OpenTofu, Terraform or Pulumi, from a CLI, Python or an MCP server (so AI agents can use it safely).

**How is it different from using Terraform directly?**
You write one small, validated spec instead of provider-specific HCL. iacforge handles rendering, running the engine, state location, JSON output and a confirmation gate. You can always `iacforge render` and take the generated files with you. It is not a replacement for Terraform modules or a registry; it covers the resource types listed per provider.

**Do I need Terraform?**
No. OpenTofu is the default engine, and Terraform and Pulumi are alternatives. You need at least one engine installed; iacforge never installs them.

**Which providers are production ready?**
`local` and `docker` are stable. `libvirt`, `hyperv`, `multipass` and `gcp` are beta. `aws` is a scaffold (schema and rendering exist; not exercised against a live account). GCP is the next main goal on the [roadmap](../ROADMAP.md).

**Can I mix providers in one stack?**
Not yet: one `spec.provider` per stack. Use one stack per provider. Multi-provider stacks are planned.

**Where is my state?**
In `.iacforge/<stack>/<engine>/` next to the spec ([Stack spec](stack-spec.md#working-directory-and-state)). It is local; remote backends are not supported yet. Do not commit it.

**Can I run it in CI?**
Yes. Use `--json`, check the exit code, and pass `--yes` only in the apply job. `validate` and `render` need no credentials or engine access to the target, so they suit pull-request checks. `plan` needs the engine and provider access.

**How do I see what will be created without applying?**
`iacforge plan` for the engine's diff, or `iacforge render` to read the generated `main.tf.json`.

**How do I get credentials into GCP/AWS?**
You do not put them in the spec. Use Application Default Credentials for GCP and the standard AWS environment or profile for AWS ([gcp](providers/gcp.md), [aws](providers/aws.md)).

**Can I use Podman instead of Docker?**
Yes, through Podman's Docker-compatible socket: enable `podman.socket` and set `providerConfig.host` ([docker](providers/docker.md)).

**Does it work on macOS?**
Yes: `local`, `docker` and `multipass` (the macOS VM path), plus the cloud providers. `libvirt` is Linux only and `hyperv` is Windows only.

**How do I add a provider or resource type?**
Subclass `ProviderAdapter` (see [contracts](../system/contracts.md), [ADR 0003](../adr/0003-plugin-contract.md) and CONTRIBUTING.md).

**How do I update or change infrastructure?**
Edit `stack.yaml` and run `iacforge plan`, then `iacforge apply --yes`. The engine computes the difference from state.

**How do I tear everything down?**
`iacforge destroy --yes` with the same spec (and engine). That deletes every resource in the stack, including volumes.

**Is the MCP server safe to give to an agent?**
`apply` and `destroy` refuse unless the call carries `confirm: true`, and the tool descriptions tell the model to plan first. Treat that as a guardrail and keep human approval on those two tools in your client ([MCP](mcp.md#confirm-gating)).

**What license?**
Apache-2.0.
