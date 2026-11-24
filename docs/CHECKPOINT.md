# Checkpoint (2026-11-24)

Goal (user, verbatim intent): build Pulumi + Terraform/OpenTofu IaC tool usable by humans,
AI agents and code; local providers on Linux/macOS/Windows first, AWS/GCP scaffolding, GCP
next; full user + system docs; public GitHub repo; commit + push; fully autonomous.

State:
- Pushed to https://github.com/bsommers/iacforge (commits 5d7161d, 0974d07).
- Code complete: engines (opentofu/terraform/pulumi), providers local/docker/libvirt/hyperv/
  multipass/gcp/aws, CLI, MCP server, CI. 164 tests pass, ruff clean.
- Docs wave: agent docs DONE (AGENTS.md, CLAUDE.md, GEMINI.md, .cursor, docs/agents/*,
  schema + test). In progress: user docs (README, docs/user-guide, examples/),
  system docs (docs/architecture.md, docs/system/*, CONTRIBUTING, CHANGELOG).
- Tracker: http://192.168.1.245:4781/ (node serve.mjs --root this repo, port 4781, setsid);
  plan in .tracker/ (gitignored). Report via
  `node ~/src/gantt-swarm-tracker/bin/track.mjs --root . <agent> <state> <pct> "msg"`.
  Never `pkill -f serve...` from a command line containing that string (kills own shell).

Dead ends: Pulumi CLI install (curl|sh) denied by permission classifier; pulumi live tests skip.

Next: v0.1 shipped (fe959d5, CI green). Tracker shows all 12 agents done. Next milestone: GCP first-class (docs/system/gcp-plan.md).
`gh run list` CI → mark tracker phases docs/ship done.
