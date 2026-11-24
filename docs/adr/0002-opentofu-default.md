# ADR 0002: OpenTofu is the default Terraform-family engine

Status: accepted (2026-11-24)

## Context
OpenTofu (MPL-2.0) and HashiCorp Terraform (BSL since 1.6) accept the same JSON
configuration syntax and the providers we use are published to both registries.

## Decision
`engine: opentofu` is the default. The `opentofu` engine runs `tofu` and falls back to
`terraform`; `engine: terraform` prefers `terraform` and falls back to `tofu`.
`IACFORGE_TF_BINARY` overrides both. One `TerraformEngine` class serves both flavors.

## Consequences
Users with only Terraform installed work unchanged. Behaviour differences between the two
binaries are out of scope unless they break our rendered JSON (covered by `tofu validate`
tests in CI).
