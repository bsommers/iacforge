# Checkpoint (2026-11-25)

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

v0.2 IN PROGRESS (user said "go" 2026-11-25):
- Contracts committed locally at 3c32e27 (not pushed): ADR 0005 spec.backend, ADR 0006 import,
  spec.Backend model, ProviderAdapter.backends/import_id, Engine.import_resource stub, gcp backends.
- 4 sonnet agents running in git worktrees (on tracker): gcp-resources (adapters/gcp.py),
  gcs-backend (render.py + engines state), import-op (core/cli/mcp/surfaces + engine import tail),
  v02-docs (docs + examples/gcp). Each commits on its own worktree branch.
- Next: merge the 4 branches into main, reconcile examples vs real property names, regen schema
  (scripts/gen_schema.py), full pytest + ruff, push, check CI, mark v02-integrate done on tracker.
Blocked on user: sandbox GCP project + Workload Identity Federation for live e2e CI job.
