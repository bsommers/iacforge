# Provider: libvirt

| | |
|---|---|
| Status | beta |
| Category | local |
| Host platforms | linux |
| Engines | opentofu, terraform, pulumi |
| Host tools | virsh, qemu-img |
| Resource types | `network`, `pool`, `vm`, `volume` |
| Upstream docs | <https://registry.terraform.io/providers/dmacvicar/libvirt/0.8.3/docs> |

Local KVM/QEMU virtual machines, networks, storage pools and volumes through libvirt (`dmacvicar/libvirt 0.8.x`; `pulumi-libvirt` for Pulumi).

- Platform: **Linux only**. Engines: OpenTofu, Terraform, Pulumi.
- Host tools: `virsh`, `qemu-img`, and a running libvirt daemon you can reach at `providerConfig.uri` (default `qemu:///system`, which needs membership of the `libvirt` group or root).
- A `vm` expands into several engine resources: a base-image volume, a copy-on-write root volume sized by `diskGb`, a cloud-init ISO and the domain itself.
- Stack networks and pools are attached explicitly with `networkRef` / `poolRef` (these also become implicit dependencies). Plain `network` / `pool` name something that already exists in libvirt.
- `sshAuthorizedKeys` is merged into the cloud-init user data; this requires user data that starts with `#cloud-config` (or no `cloudInit` at all).

Run `iacforge schema libvirt --json` for the machine-readable JSON Schema of everything below. Unknown keys are rejected, so typos fail at `validate`.

Property names are camelCase as written in the spec. Defaults shown as "unset" mean the property is omitted and the provider or engine default applies.

## providerConfig

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `uri` | string | no | `"qemu:///system"` | libvirt connection URI. |

## Resource types

### `network`

Terraform/OpenTofu type: `libvirt_network`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `mode` | string (pattern `^(nat\|isolated\|bridge)$`) | no | `"nat"` |  |
| `cidr` | string | no | unset | e.g. 192.168.150.0/24 (nat/isolated). |
| `dhcp` | boolean | no | `true` |  |
| `autostart` | boolean | no | `true` |  |
| `bridge` | string | no | unset | Host bridge device (required for mode=bridge). |
| `domain` | string | no | unset |  |

Outputs: `id`, `name`

### `pool`

Terraform/OpenTofu type: `libvirt_pool`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `path` | string | yes | - | Directory backing the pool. |

Outputs: `id`, `name`

### `vm`

Terraform/OpenTofu type: `libvirt_domain`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `memoryMb` | integer (min 64) | no | `1024` |  |
| `vcpu` | integer (min 1) | no | `1` |  |
| `image` | string | yes | - | Base image URL or local path (qcow2/img). |
| `diskGb` | integer (min 1) | no | unset | Root disk size; default = image size. |
| `network` | string | no | `"default"` | Existing libvirt network name. |
| `networkRef` | string | no | unset | Stack `network` resource to attach to (overrides `network`). |
| `pool` | string | no | `"default"` | Existing libvirt storage pool name. |
| `poolRef` | string | no | unset | Stack `pool` resource for volumes (overrides `pool`). |
| `cloudInit` | `CloudInit` | no | unset |  |
| `sshAuthorizedKeys` | list of string | no | `[]` |  |
| `autostart` | boolean | no | `false` |  |

`CloudInit` object:

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `userData` | string | yes | - | cloud-config user-data text. |
| `metaData` | string | no | unset |  |

Outputs: `id`, `ip`, `name`

### `volume`

Terraform/OpenTofu type: `libvirt_volume`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `pool` | string | no | `"default"` | Existing libvirt storage pool name. |
| `poolRef` | string | no | unset |  |
| `sizeGb` | integer (min 1) | no | unset |  |
| `source` | string | no | unset | Image URL or path to import. |

Outputs: `id`, `name`


## Validation rules

- `network`: mode `bridge` requires `bridge`; modes `nat` and `isolated` require `cidr`. `mode` must be one of `nat`, `isolated`, `bridge`.
- `volume`: needs `sizeGb` or `source`.
- `vm.sshAuthorizedKeys` requires `cloudInit.userData` to start with `#cloud-config`.

## Outputs

Outputs listed under each resource type are returned by `apply` and `outputs` as `{resource-name: {key: value}}`, for example `iacforge outputs` prints `{"web": {"id": "...", "name": "web"}}`.

## Example

See [`examples/libvirt/stack.yaml`](../../../examples/libvirt/stack.yaml):

```yaml
# KVM/QEMU VM on a NAT network. Linux host with libvirt; set sshAuthorizedKeys to your key.
apiVersion: iacforge/v1
kind: Stack
metadata:
  name: libvirt-demo
spec:
  provider: libvirt
  resources:
  - name: labpool
    type: pool
    properties:
      path: /var/lib/libvirt/images/lab
  - name: labnet
    type: network
    properties:
      mode: nat
      cidr: 192.168.150.0/24
  - name: data
    type: volume
    properties:
      poolRef: labpool
      sizeGb: 5
  - name: web
    type: vm
    properties:
      image: https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img
      memoryMb: 2048
      vcpu: 2
      diskGb: 20
      networkRef: labnet
      poolRef: labpool
      sshAuthorizedKeys:
      - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA-replace-with-your-public-key you@host
```
