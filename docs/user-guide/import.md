# Importing existing resources

`iacforge import` adopts a resource that already exists into a stack's state, so you can manage it without recreating it. Contract: [ADR 0006](../adr/0006-import-operation.md).

## How it works

1. Declare the resource in the spec first. Strict validation tells you which properties are required.
2. Run import with the stack resource name. iacforge works out the provider's import ID, writes it to state, then runs `plan`.
3. Read the plan. Differences between the spec and the real resource show up as changes a first `apply` would make. Edit the spec until the plan is empty.

Import writes state, so it is gated like `apply`: it needs confirmation.

## CLI

```sh
iacforge import stack.yaml --resource web --yes
iacforge import stack.yaml --resource web --id projects/p/zones/z/instances/web --yes
```

| Option | Meaning |
|---|---|
| `--resource NAME` | Resource name in the stack (required). |
| `--id ID` | Provider import ID. Omit to derive it. |
| `--yes` | Confirm. Without it, exit code 5 (`not_confirmed`). |
| `--engine`, `--workdir` | As for the other commands. |

## MCP

Tool `iacforge_import` with `spec`, `resource`, optional `id`, `engine`, `workdir`, and `confirm: true`. Agents should run `iacforge_validate` first, and `iacforge_plan` after.

## Python

```python
from iacforge import core
r = core.import_resource("stack.yaml", "web", confirm=True)
r["imported"]      # {"resource": "web", "address": "google_compute_instance.web", "id": "..."}
r["plan"]          # what a first apply would change
```

## Id derivation

When `id` is omitted, core asks the provider adapter (`import_id`) to build the ID from the resource's properties and `providerConfig`. The `gcp` adapter does this for every resource type, for example `projects/{project}/zones/{zone}/instances/{name}` for a `vm`. Adapters without a derivation fail with `unsupported` unless you pass `--id`. An explicit `--id` always wins.

## Result and follow-up plan

The result envelope adds to the usual `plan` data:

```json
{"imported": {"resource": "web", "address": "google_compute_instance.web", "id": "projects/p/zones/z/instances/web"},
 "changes": {"add": 0, "change": 1, "destroy": 0},
 "plan": ["..."]}
```

A non-empty plan after import means the spec and reality differ. Do not apply blindly: a `change` may modify the live resource, and a `destroy`/replace will delete it. Fix the spec first.

## Notes

- Terraform/OpenTofu runs `import` against `<tf type>.<tf id(name)>`; Pulumi imports by type token and ID with the logical name equal to the resource name.
- Importing needs the same credentials and, for a remote [state backend](state-backends.md), access to that bucket.
- Import does not discover resources and does not generate a spec; write the declaration yourself.
