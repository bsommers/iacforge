# Provider: hyperv

| | |
|---|---|
| Status | beta |
| Category | local |
| Host platforms | windows |
| Engines | opentofu, terraform |
| Host tools | powershell |
| Resource types | `switch`, `vhd`, `vm` |
| Upstream docs | <https://registry.terraform.io/providers/taliesins/hyperv/latest/docs> |

Hyper-V virtual machines, switches and VHDs on a Windows host (`taliesins/hyperv`).

- Platform: **Windows only**. Engines: OpenTofu and Terraform only (no Pulumi support).
- Host tools: PowerShell, Hyper-V enabled, and WinRM reachable at `providerConfig.host` (default `127.0.0.1:5986`, HTTPS).
- Run from an elevated session on the Hyper-V host.
- **Credentials:** export `HYPERV_USER` / `HYPERV_PASSWORD`. There is deliberately no `password` field in `providerConfig` (it would be rendered into `main.tf.json` and state in plain text).
- Stack switches and VHDs are attached with `switchRef` / `vhdRef` (implicit dependencies). Plain `switch` names an existing Hyper-V switch.

Run `iacforge schema hyperv --json` for the machine-readable JSON Schema of everything below. Unknown keys are rejected, so typos fail at `validate`.

Property names are camelCase as written in the spec. Defaults shown as "unset" mean the property is omitted and the provider or engine default applies.

## providerConfig

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `host` | string | no | `"127.0.0.1"` |  |
| `port` | integer (min 1, max 65535) | no | `5986` |  |
| `https` | boolean | no | `true` |  |
| `insecure` | boolean | no | `false` |  |
| `user` | string | no | unset | Falls back to env HYPERV_USER. |
| `useNtlm` | boolean | no | `true` |  |

## Resource types

### `switch`

Terraform/OpenTofu type: `hyperv_network_switch`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | string (pattern `^(Internal\|Private\|External)$`) | no | `"Internal"` |  |
| `netAdapterNames` | list of string | no | `[]` |  |

Outputs: `name`

### `vhd`

Terraform/OpenTofu type: `hyperv_vhd`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `path` | string | yes | - | Destination .vhdx path on the Hyper-V host. |
| `sizeGb` | integer (min 1) | no | unset |  |
| `source` | string | no | unset | Existing VHD to copy from. |

Outputs: `path`

### `vm`

Terraform/OpenTofu type: `hyperv_machine_instance`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `generation` | integer (min 1, max 2) | no | `2` |  |
| `memoryMb` | integer (min 32) | no | `1024` |  |
| `vcpu` | integer (min 1) | no | `1` |  |
| `switch` | string | no | unset | Existing Hyper-V switch name. |
| `switchRef` | string | no | unset | Stack `switch` resource. |
| `vhdPath` | string | no | unset | Existing VHDX path to attach. |
| `vhdRef` | string | no | unset | Stack `vhd` resource to attach. |
| `vhdSizeGb` | integer (min 1) | no | unset | Create a VHD of this size next to the VM (needs vhdPath). |
| `dynamicMemory` | boolean | no | `false` |  |

Outputs: `id`, `name`


## Validation rules

- `vm`: `switch` and `switchRef` are mutually exclusive; `vhdRef` excludes `vhdPath` / `vhdSizeGb`; `vhdSizeGb` requires `vhdPath`.
- `switch`: `type` is `Internal`, `Private` or `External`; `External` requires `netAdapterNames`.
- `vhd`: needs `sizeGb` or `source`.

## Outputs

Outputs listed under each resource type are returned by `apply` and `outputs` as `{resource-name: {key: value}}`, for example `iacforge outputs` prints `{"web": {"id": "...", "name": "web"}}`.

## Example

See [`examples/hyperv/stack.yaml`](../../../examples/hyperv/stack.yaml):

```yaml
# Hyper-V VM + switch + VHD. Windows host, elevated; set HYPERV_USER/HYPERV_PASSWORD.
apiVersion: iacforge/v1
kind: Stack
metadata:
  name: hyperv-demo
spec:
  provider: hyperv
  resources:
  - name: labswitch
    type: switch
    properties:
      type: Internal
  - name: disk
    type: vhd
    properties:
      path: C:\VMs\lab\disk.vhdx
      sizeGb: 40
  - name: lab1
    type: vm
    properties:
      generation: 2
      memoryMb: 2048
      vcpu: 2
      switchRef: labswitch
      vhdRef: disk
```
