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

## v0.2 (next): GCP first-class
- next: GCP live end-to-end tests in a sandbox project (opt-in CI job using Workload
  Identity Federation, no long-lived keys)
- next: GCP resources: Cloud Run service, GKE Autopilot cluster, Cloud SQL, Artifact
  Registry, Secret Manager secret (reference only, never values), IAM bindings
- next: remote state: GCS backend for Terraform, `gs://` backend for Pulumi
- next: `iacforge import` for adopting existing GCP resources

## v0.3: hardening
- planned: drift detection command (`iacforge drift`)
- planned: policy hooks (deny public buckets, required labels) evaluated before apply
- planned: multi-provider stacks (e.g. GCP + docker in one spec)
- planned: AWS promoted from scaffold to beta (EKS, RDS, IAM roles)

## Ideas
- idea: Azure provider; Proxmox; Lima/UTM native macOS VMs; Podman-first adapter
- idea: HTTP API surface (REST) alongside MCP
- idea: stack composition / modules (`include:`)
