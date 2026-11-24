# CLAUDE.md

See [AGENTS.md](AGENTS.md) for all repo guidance (commands, architecture, invariants, pitfalls).

Claude-specific notes:
- Use `.venv/bin/ruff` and `.venv/bin/pytest` if the venv is not activated.
- Put scratch workdirs, cargo/venv/build output under `/datanapps/claude-tmp`, never `/tmp`.
- To provision infrastructure with iacforge (rather than edit it), follow
  `docs/agents/using-iacforge.md`; never run apply/destroy without human intent.
- Do not commit unless asked.
