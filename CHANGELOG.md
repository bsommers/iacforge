# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-24

First release.

### Added

- Provider-neutral stack spec `iacforge/v1` (YAML or JSON) with strict validation, dependency
  ordering (`dependsOn` plus implicit references) and JSON Schema export (`iacforge schema`).
- Provider adapter contract (`ProviderAdapter`) with a shared contract test suite and an
  `EXAMPLES` requirement for every provider.
- Engines: OpenTofu/Terraform (renders deterministic `main.tf.json`; `tofu` preferred, `terraform`
  fallback, `IACFORGE_TF_BINARY` override) and Pulumi (Automation API with a local file backend, plus
  an ejectable Pulumi project).
- Providers: `local` (files), `docker` (image, container, network, volume), `libvirt`, `hyperv`
  (Windows, Terraform only), `multipass` (Terraform only), `gcp` (beta: network, subnet, firewall,
  vm, bucket, service_account), `aws` (scaffold: vpc, subnet, security_group, vm, bucket).
- Surfaces: `iacforge` CLI with a `--json` envelope and stable exit codes, Python API
  (`iacforge.core`), and `iacforge-mcp` MCP server (stdio) exposing one tool per operation.
- Operations: `version`, `providers`, `schema`, `doctor`, `init`, `validate`, `render`, `plan`,
  `outputs`, `apply`, `destroy`.
- Confirmation gate for `apply` and `destroy` enforced in core (`--yes` / `confirm=true`).
- Typed errors with stable codes (`invalid_spec`, `unknown_provider`, `unsupported`,
  `tool_missing`, `engine_failed`, `not_confirmed`) and exit codes 0-5.
- Install scripts (`scripts/install.sh`, `scripts/install.ps1`) and GitHub Actions CI on
  Linux, macOS and Windows (Python 3.11 and 3.13) with SHA-pinned actions.
- Architecture decision records 0001-0004 and a roadmap.

[Unreleased]: https://github.com/bsommers/iacforge/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/bsommers/iacforge/releases/tag/v0.1.0
