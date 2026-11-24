# Provider: local

| | |
|---|---|
| Status | stable |
| Category | local |
| Host platforms | darwin, linux, windows |
| Engines | opentofu, terraform, pulumi |
| Host tools | none (engine only) |
| Resource types | `file` |
| Upstream docs | <https://registry.terraform.io/providers/hashicorp/local/latest/docs> |

Writes files on the host filesystem (`hashicorp/local`). It is the reference provider and the quickest way to try iacforge: no daemon, no hypervisor, no cloud account.

- Platforms: Linux, macOS, Windows. Engines: OpenTofu, Terraform, Pulumi.
- Host tools: only the engine binary.
- Relative `path` values resolve against the **engine workdir** (`.iacforge/<stack>/<engine>/`), not your current directory. Use an absolute path to write elsewhere.

Run `iacforge schema local --json` for the machine-readable JSON Schema of everything below. Unknown keys are rejected, so typos fail at `validate`.

Property names are camelCase as written in the spec. Defaults shown as "unset" mean the property is omitted and the provider or engine default applies.

## providerConfig

This provider takes no configuration. Leave `providerConfig` empty (`{}`).

## Resource types

### `file`

Terraform/OpenTofu type: `local_file`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `path` | string | yes | - | Destination path; relative paths resolve against the workdir. |
| `content` | string | no | `""` | File content (UTF-8). |
| `filePermission` | string (pattern `^0?[0-7]{3}$`) | no | `"0644"` |  |

Outputs: `id`, `path`



## Outputs

Outputs listed under each resource type are returned by `apply` and `outputs` as `{resource-name: {key: value}}`, for example `iacforge outputs` prints `{"web": {"id": "...", "name": "web"}}`.

## Example

See [`examples/local/stack.yaml`](../../../examples/local/stack.yaml):

```yaml
# Writes a file. No daemon, no cloud. Needs only tofu/terraform.
apiVersion: iacforge/v1
kind: Stack
metadata:
  name: local-demo
spec:
  provider: local
  resources:
  - name: hello
    type: file
    properties:
      path: out/hello.txt
      content: 'hello from iacforge

        '
```
