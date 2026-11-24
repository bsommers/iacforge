# ADR 0003: Providers are adapters behind a small contract; engines own all side effects

Status: accepted (2026-11-24)

## Decision
- A provider adapter (`src/iacforge/adapters/<name>.py`) is pure translation: typed
  property models, `tf_resource()` returning JSON blocks, optional `pulumi_resource()`.
  It never runs processes or reads state.
- Engines (`src/iacforge/engines/`) own subprocesses, state and workdirs, and take an
  injectable `Runner` so they are testable without binaries.
- Host-OS differences live in adapter capability metadata (`platforms`,
  `required_tools`), never as `if platform == ...` branches in core logic.
- One shared contract suite (`tests/test_adapter_contract.py`) runs against every adapter,
  including a real `tofu validate` of each adapter's `EXAMPLES`.

## Consequences
Adding a provider is one module plus one registry line. Contract growth needs an ADR.
