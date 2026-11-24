# Provider: docker

| | |
|---|---|
| Status | stable |
| Category | local |
| Host platforms | darwin, linux, windows |
| Engines | opentofu, terraform, pulumi |
| Host tools | docker |
| Resource types | `container`, `image`, `network`, `volume` |
| Upstream docs | <https://registry.terraform.io/providers/kreuzwerker/docker/latest/docs> |

Containers, images, networks and volumes through the Docker API (`kreuzwerker/docker ~> 3.0`; `pulumi-docker` for Pulumi).

- Platforms: Linux, macOS, Windows. Engines: OpenTofu, Terraform, Pulumi.
- Host tools: a reachable Docker-API daemon (`docker` must be on `PATH` for `iacforge doctor` to report ready).
- Daemon selection: `providerConfig.host`, else `DOCKER_HOST`, else the platform default socket.

```yaml
host: unix:///var/run/docker.sock                    # Linux / Docker Desktop (mac)
host: unix:///Users/me/.colima/default/docker.sock   # Colima
host: npipe:////./pipe/docker_engine                 # Windows Docker Desktop
host: unix:///run/user/1000/podman/podman.sock       # rootless Podman (Docker-compatible socket)
```

Podman works through its Docker-compatible socket (`systemctl --user enable --now podman.socket`).

**Registry credentials:** `registryAuth` entries accept only `address` and `configFile`; usernames and passwords are deliberately not accepted so they never land in `main.tf.json` or state. Run `docker login <registry>` to populate `~/.docker/config.json` (or point `configFile` at another config).

A container takes its image either as a plain reference (`image: nginx:1.27`) or as the name of an `image` resource in the stack (`imageFrom: base`), never both.

Run `iacforge schema docker --json` for the machine-readable JSON Schema of everything below. Unknown keys are rejected, so typos fail at `validate`.

Property names are camelCase as written in the spec. Defaults shown as "unset" mean the property is omitted and the provider or engine default applies.

## providerConfig

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `host` | string | no | unset | Docker daemon endpoint; default: DOCKER_HOST / platform default. |
| `registryAuth` | list of `RegistryAuth` | no | `[]` |  |

`RegistryAuth` object:

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `address` | string | yes | - | Registry host, e.g. ghcr.io or registry-1.docker.io. |
| `configFile` | string | no | unset | Path to a docker config.json holding credentials. |

## Resource types

### `container`

Terraform/OpenTofu type: `docker_container`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `image` | string | no | unset | Image reference (e.g. alpine:3.20). |
| `imageFrom` | string | no | unset | Name of an `image` resource in the stack. |
| `name` | string | no | unset | Container name; defaults to the resource name. |
| `command` | list of string | no | unset |  |
| `env` | map of string | no | `{}` |  |
| `ports` | list of `PortMap` | no | `[]` |  |
| `volumes` | list of `VolumeMount` | no | `[]` |  |
| `networks` | list of string | no | `[]` | Names of `network` resources in the stack. |
| `restart` | enum: `no`, `on-failure`, `always`, `unless-stopped` | no | unset |  |
| `labels` | map of string | no | `{}` |  |
| `memoryMb` | integer (min 4) | no | unset |  |

`PortMap` object:

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `internal` | integer (min 1, max 65535) | yes | - |  |
| `external` | integer (min 1, max 65535) | no | unset |  |
| `protocol` | enum: `tcp`, `udp`, `sctp` | no | `"tcp"` |  |
| `ip` | string | no | unset |  |

`VolumeMount` object:

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `volume` | string | no | unset | Name of a `volume` resource in the stack. |
| `hostPath` | string | no | unset | Bind-mount host path. |
| `containerPath` | string (minLen 1) | yes | - |  |
| `readOnly` | boolean | no | `false` |  |

Outputs: `id`, `ip_address`, `ip_addresses`, `name`

### `image`

Terraform/OpenTofu type: `docker_image`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string (minLen 1) | yes | - | Image reference, e.g. nginx:1.27. |
| `keepLocally` | boolean | no | `false` | Keep the image in the daemon on destroy. |

Outputs: `id`, `image_id`, `name`

### `network`

Terraform/OpenTofu type: `docker_network`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | no | unset | Network name; defaults to the resource name. |
| `driver` | string | no | `"bridge"` |  |
| `internal` | boolean | no | `false` |  |
| `subnet` | string (pattern `^[0-9a-fA-F:.]+/\d{1,3}$`) | no | unset |  |
| `labels` | map of string | no | `{}` |  |

Outputs: `id`, `name`

### `volume`

Terraform/OpenTofu type: `docker_volume`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | no | unset | Volume name; defaults to the resource name. |
| `driver` | string | no | `"local"` |  |
| `labels` | map of string | no | `{}` |  |

Outputs: `name`


## Validation rules

- A `container` needs exactly one of `image` / `imageFrom`.
- Each `volumes[]` entry needs exactly one of `volume` / `hostPath`.
- `imageFrom`, `networks[]` and `volumes[].volume` must name stack resources of type `image`, `network` and `volume` respectively; duplicate entries in `networks` are rejected.

## Outputs

Outputs listed under each resource type are returned by `apply` and `outputs` as `{resource-name: {key: value}}`, for example `iacforge outputs` prints `{"web": {"id": "...", "name": "web"}}`.

## Example

See [`examples/docker/stack.yaml`](../../../examples/docker/stack.yaml):

```yaml
# nginx on a private network with a named volume. Needs a running Docker daemon.
apiVersion: iacforge/v1
kind: Stack
metadata:
  name: docker-demo
spec:
  provider: docker
  resources:
  - name: net
    type: network
    properties:
      labels:
        env: dev
  - name: data
    type: volume
    properties:
      labels:
        env: dev
  - name: base
    type: image
    properties:
      name: nginx:1.27-alpine
      keepLocally: true
  - name: web
    type: container
    properties:
      imageFrom: base
      env:
        B: '2'
        A: '1'
      ports:
      - internal: 80
        external: 8089
      volumes:
      - volume: data
        containerPath: /data
      networks:
      - net
      restart: unless-stopped
      labels:
        app: web
      memoryMb: 128
```
