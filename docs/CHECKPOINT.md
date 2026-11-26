# Checkpoint (2026-11-24)

Goal (user, verbatim intent): build Pulumi + Terraform/OpenTofu IaC tool usable by humans,
AI agents and code; local providers on Linux/macOS/Windows first, AWS/GCP scaffolding, GCP
next; full user + system docs; public GitHub repo; commit + push; fully autonomous.

State:
- v0.1 shipped: https://github.com/bsommers/iacforge, main == origin/main at 99dc33a, tree clean,
  CI 6/6 green (ubuntu/macos/windows x py3.11/3.13). 166 tests pass (3 pulumi-live skip), ruff clean.
- Providers: local, docker, libvirt, hyperv, multipass (stable/beta), gcp (beta), aws (scaffold).
  Engines: opentofu (default), terraform, pulumi. Surfaces: CLI, Python API, MCP (10 tools).
- No background jobs of this session except the tracker server.
- Tracker: http://192.168.1.245:4781/ (node ~/src/gantt-swarm-tracker/bin/serve.mjs --root this
  repo --host 0.0.0.0 --port 4781, setsid). Plan in .tracker/plan.json (gitignored), 12 v0.1 agents
  all done. Report via
  `node ~/src/gantt-swarm-tracker/bin/track.mjs --root . <agent> start|progress|done <pct> "msg"`.
  Add every new agent to plan.json first. Never `pkill -f serve...` from a command line containing
  that string (kills own shell).

Dead ends: Pulumi CLI install (curl|sh) denied by permission classifier; pulumi live tests skip.

Next: v0.2 GCP first-class (docs/system/gcp-plan.md, ROADMAP v0.2). User has not yet said "go".
1. Write ADR 0005 for `spec.backend` (local | gcs) — contract change shared by items 2-3.
2. Then parallel agents (register on tracker; explicit model per CLAUDE.md):
   resources (cloud_run_service, gke_autopilot, cloud_sql, artifact_registry, secret, iam_binding
   in adapters/gcp.py, both engines), GCS backend (spec/render/engines), `iacforge import`
   (CLI+API+MCP, surface parity), docs/examples.
3. Integrate, full test + ruff, push, confirm CI green, promote gcp to stable once live e2e exists.
Blocked on user: sandbox GCP project + Workload Identity Federation for live e2e CI job.
Commits/pushes for v0.2 were part of the original autonomous goal; outward-facing approvals
otherwise treated as expired after compaction.
