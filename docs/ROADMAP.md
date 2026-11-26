# Roadmap

Status key: done · next · planned · idea

## v0.1 (this release): foundation
- done: stack spec `iacforge/v1`, JSON Schema export, provider-adapter contract
- done: engines: OpenTofu/Terraform (`main.tf.json`), Pulumi (Automation API + ejectable project)
- done: local providers: `local` (files), `docker` (Linux/macOS/Windows), `libvirt` (Linux),
  `hyperv` (Windows), `multipass` (Linux/macOS/Windows VMs)
- done: cloud providers: `gcp` (beta), `aws` (scaffold)
- done: surfaces: CLI with JSON envelope, Python API, MCP server for AI agents
- done: CI on Linux/macOS/Windows

## v0.2 (in progress): GCP first-class
- in progress: GCP resources: `artifact_registry`, `secret` (reference only, never values),
  `cloud_run_service`, `gke_autopilot`, `cloud_sql`, `iam_binding`; `providerConfig.enableApis`
  ([gcp-plan.md](system/gcp-plan.md), [provider page](user-guide/providers/gcp.md))
- in progress: remote state: `spec.backend` with GCS for Terraform/OpenTofu and `gs://` for Pulumi
  ([ADR 0005](adr/0005-spec-backend.md), [guide](user-guide/state-backends.md))
- in progress: `iacforge import` for adopting existing resources
  ([ADR 0006](adr/0006-import-operation.md), [guide](user-guide/import.md))
- next: GCP live end-to-end tests in a sandbox project (opt-in CI job using Workload
  Identity Federation, no long-lived keys)
- next: promote `gcp` from beta to stable (criteria in gcp-plan.md section 5)

## v0.3: hardening
- planned: drift detection command (`iacforge drift`)
- planned: policy hooks (deny public buckets, required labels) evaluated before apply
- planned: multi-provider stacks (e.g. GCP + docker in one spec)
- planned: AWS promoted from scaffold to beta (EKS, RDS, IAM roles)

## Ideas
- idea: Azure provider; Proxmox; Lima/UTM native macOS VMs; Podman-first adapter
- idea: HTTP API surface (REST) alongside MCP
- idea: stack composition / modules (`include:`)
