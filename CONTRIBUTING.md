# Contributing to iacforge

Thanks for helping. Read [docs/architecture.md](docs/architecture.md) first; the invariants there
(pure adapters, engines own side effects, gating in core, deterministic render) are what review
checks.

## Dev setup

Requirements: Python 3.10+ (CI tests 3.11 and 3.13), [uv](https://docs.astral.sh/uv/), and
[OpenTofu](https://opentofu.org/docs/intro/install/) for the integration tests. Pulumi and Docker
are optional.

```bash
git clone https://github.com/bsommers/iacforge && cd iacforge
uv sync --extra dev --extra mcp        # add --extra pulumi (or pulumi-docker, pulumi-gcp, ...) if needed
uv run iacforge doctor                 # see which tools the host has
```

## Gates

Both must pass before you open a PR (CI runs them on Linux, macOS and Windows):

```bash
uv run ruff check .
uv run pytest -q
```

Offline or without OpenTofu: `uv run pytest -q -m "not tofu"`. Marker details and fakes are in
[docs/system/testing.md](docs/system/testing.md). Ruff is configured in `pyproject.toml` (line
length 100, rules E F W I B UP RUF).

## Making a change

- Branch from `main`; keep PRs focused.
- Behaviour goes in `src/iacforge/core.py`; CLI and MCP only translate. A new operation must be added
  to `src/iacforge/surfaces.py` and appear on both the CLI and MCP (or carry a documented
  exclusion); `tests/test_surface_parity.py` enforces this.
- Error `code` strings and exit codes in `src/iacforge/errors.py` are a public contract; changing
  them is a breaking change.
- Add or update tests with the change, and update docs and `CHANGELOG.md` (Unreleased section).
- Changes to the adapter or engine contract need an ADR in `docs/adr/` (next number, same format as
  the existing ones).

## Commit style

Short imperative subject (about 72 characters), no trailing period, optional body explaining why.
Examples from the history: `Add engines, providers (...)`, `Core contracts: spec, ...`. One logical
change per commit. Do not commit state or build output (`.iacforge/`, `*.tfstate`, `.terraform/`).

## Adding a provider

Step by step with a worked example: [docs/system/adding-a-provider.md](docs/system/adding-a-provider.md).
In short: create `src/iacforge/adapters/<name>.py` with an `ADAPTER` and `EXAMPLES`, register it in
`ADAPTER_MODULES` (`src/iacforge/adapters/__init__.py`), let `tests/test_adapter_contract.py` run
against it, add provider tests and a docs page. Reference contract: [docs/system/contracts.md](docs/system/contracts.md).

## Adding an engine

Subclass `Engine` (`src/iacforge/engines/base.py`), route all processes through the injected
`Runner`, register in `src/iacforge/engines/__init__.py`, write fake-runner tests modelled on
`tests/test_engine_terraform.py`, and add an ADR. See [docs/system/engines.md](docs/system/engines.md#adding-an-engine).

## Security

Never put credentials in specs, tests or examples. Report vulnerabilities privately to the
maintainer rather than in a public issue. See [docs/system/security.md](docs/system/security.md).
