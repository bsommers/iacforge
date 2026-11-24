# Provider: multipass

| | |
|---|---|
| Status | beta |
| Category | local |
| Host platforms | darwin, linux, windows |
| Engines | opentofu, terraform |
| Host tools | multipass |
| Resource types | `vm` |
| Upstream docs | <https://registry.terraform.io/providers/larstobi/multipass/latest/docs> |

Ubuntu VMs through Canonical Multipass (`larstobi/multipass`). The cross-platform local VM option and the main VM path on macOS.

- Platforms: Linux, macOS, Windows. Engines: OpenTofu and Terraform only (no Pulumi support).
- Host tools: the `multipass` CLI (<https://multipass.run/install>).
- `cloudInit` text is written next to the rendered config as `<name>-cloud-init.yaml` and passed to Multipass as `cloudinit_file`.
- `memory` (for example `2G`, `1536M`) and `memoryGb` are mutually exclusive; if neither is set the VM gets 1G.

Run `iacforge schema multipass --json` for the machine-readable JSON Schema of everything below. Unknown keys are rejected, so typos fail at `validate`.

Property names are camelCase as written in the spec. Defaults shown as "unset" mean the property is omitted and the provider or engine default applies.

## providerConfig

This provider takes no configuration. Leave `providerConfig` empty (`{}`).

## Resource types

### `vm`

Terraform/OpenTofu type: `multipass_instance`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `image` | string | no | `"24.04"` | Image alias, e.g. 24.04, 22.04, or a URL. |
| `cpus` | integer (min 1) | no | `1` |  |
| `memoryGb` | number (> 0) | no | unset |  |
| `memory` | string (pattern `^\d+(\.\d+)?[KMG]i?B?$`) | no | unset | e.g. 2G or 1536M; overrides memoryGb. |
| `diskGb` | integer (min 1) | no | `5` |  |
| `cloudInit` | string | no | unset | cloud-config user-data text. |

Outputs: `ipv4`, `name`


## Validation rules

- Set only one of `memory` and `memoryGb`.

## Outputs

Outputs listed under each resource type are returned by `apply` and `outputs` as `{resource-name: {key: value}}`, for example `iacforge outputs` prints `{"web": {"id": "...", "name": "web"}}`.

## Example

See [`examples/multipass/stack.yaml`](../../../examples/multipass/stack.yaml):

```yaml
# Ubuntu VM with cloud-init. Needs the multipass CLI.
apiVersion: iacforge/v1
kind: Stack
metadata:
  name: multipass-demo
spec:
  provider: multipass
  resources:
  - name: dev
    type: vm
    properties:
      image: '24.04'
      cpus: 2
      memoryGb: 2
      diskGb: 10
      cloudInit: "#cloud-config\npackages:\n  - htop\n"
```
