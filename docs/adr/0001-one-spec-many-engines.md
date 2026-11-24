# ADR 0001: One provider-neutral spec, rendered to multiple engines

Status: accepted (2026-11-24)

## Context
We need humans, AI agents and other programs to provision infrastructure on local
hypervisors/container runtimes (Linux, macOS, Windows) and on clouds (GCP next, AWS), using
OpenTofu/Terraform and Pulumi. Writing HCL or Pulumi code directly forces every caller to
learn each provider's schema and each engine's workflow, and is hard for agents to
generate safely.

## Options considered
1. **Generate HCL text from templates.** Familiar output, but templating HCL means escaping
   rules and string concatenation; hard to make deterministic.
2. **Wrap Terraform modules only.** Ties us to one engine; Pulumi users excluded.
3. **One YAML/JSON stack spec → Terraform JSON (`main.tf.json`) or a Pulumi program
   (chosen).** Terraform JSON syntax is a first-class, serializer-produced format: no
   escaping, deterministic with sorted keys, and validated by the real `tofu validate`.
   The same validated spec drives a Pulumi Automation API inline program.

## Decision
Option 3. Validation (pydantic models per provider) happens once, before any engine runs.
Engines are swappable per stack (`spec.engine`) or per command (`--engine`).

## Consequences
- The spec covers a curated subset of each provider. Exotic features need a new property
  or resource type in the adapter (by design: every property is typed and documented).
- Rendered files are ejectable: `iacforge render` leaves a plain Terraform/Pulumi project a
  human can take over.
- Reversal cost: medium. Adapters are small translation layers; dropping an engine means
  deleting one module.
