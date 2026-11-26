# ADR 0006: `import` adopts existing resources through a gated core operation

Status: accepted (2026-11-25)

## Decision
- Core: `import_resource(spec, resource, id=None, engine=None, workdir=None, confirm=False,
  runner=None)`. It writes state, so it is gated by `confirm` like `apply` (ADR 0004).
  Surfaces: CLI `iacforge import SPEC --resource NAME [--id ID] [--yes]`, MCP `iacforge_import`,
  `surfaces.OPERATIONS` entry `("import_resource", "import", "iacforge_import")`.
- The resource must already be declared in the spec (strict validation tells the user which
  properties are needed). `resource` is the stack resource name.
- `id` is the provider's import ID. When omitted, core asks the adapter:
  `ProviderAdapter.import_id(res, props, config) -> str`; the default raises `UnsupportedError`
  (code `unsupported`). gcp implements it for every type.
- Engine contract: `Engine.import_resource(b, workdir, resource, import_id) -> {"log": str}`.
  Terraform runs `<tofu> import -input=false -no-color <tf_type>.<tf_id(name)> <id>`;
  Pulumi uses the Automation API import of type token + id with logical name = resource name.
- After importing, core runs `plan` and returns
  `{..., "imported": {"resource", "address", "id"}, "changes": ..., "plan": [...]}` so the caller
  sees what a first `apply` would change.

## Consequences
One more mutating operation; the same gate and error codes apply. Adapters without `import_id`
still support import when the caller passes `id` explicitly.
