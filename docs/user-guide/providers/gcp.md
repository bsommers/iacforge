# Provider: gcp

| | |
|---|---|
| Status | beta |
| Category | cloud |
| Host platforms | darwin, linux, windows |
| Engines | opentofu, terraform, pulumi |
| Host tools | none (engine only) |
| Resource types | `bucket`, `firewall`, `network`, `service_account`, `subnet`, `vm` |
| Upstream docs | <https://registry.terraform.io/providers/hashicorp/google/latest/docs> |

Google Cloud: VPC networks, subnets, firewalls, Compute Engine VMs, Cloud Storage buckets and service accounts (`hashicorp/google ~> 6.0`; `pulumi-gcp` for Pulumi). **Status: beta**; the next main development goal (see the roadmap).

- Platforms: Linux, macOS, Windows. Engines: OpenTofu, Terraform, Pulumi.
- Host tools: none required by iacforge itself; install the `gcloud` CLI to authenticate.
- **Authentication:** never put credentials in a spec. Use Application Default Credentials:
  `gcloud auth application-default login` for a workstation, `GOOGLE_APPLICATION_CREDENTIALS` pointing to a key file for automation, or workload identity on GCP/CI. `providerConfig.project` is the only required setting.
- References: `subnet.network`, `firewall.network`, `vm.subnet`, `vm.network`, `vm.serviceAccount` name other stack resources and become implicit dependencies; iacforge checks the referenced resource has the right type.
- Planning and applying creates billable resources. Use `iacforge plan` first and `iacforge destroy` when done.

Run `iacforge schema gcp --json` for the machine-readable JSON Schema of everything below. Unknown keys are rejected, so typos fail at `validate`.

Property names are camelCase as written in the spec. Defaults shown as "unset" mean the property is omitted and the provider or engine default applies.

## providerConfig

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `project` | string (minLen 1) | yes | - | GCP project id (credentials come from ADC, never the spec). |
| `region` | string | no | `"us-central1"` |  |
| `zone` | string | no | `"us-central1-a"` |  |
| `labels` | map of string | no | `{}` | Default labels merged into labelled resources. |

## Resource types

### `bucket`

Terraform/OpenTofu type: `google_storage_bucket`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `bucketName` | string | no | unset | Globally unique; default: resource name. |
| `location` | string | no | unset | Default: providerConfig.region. |
| `storageClass` | enum: `STANDARD`, `NEARLINE`, `COLDLINE`, `ARCHIVE` | no | `"STANDARD"` |  |
| `versioning` | boolean | no | `false` |  |
| `uniformBucketLevelAccess` | boolean | no | `true` |  |
| `forceDestroy` | boolean | no | `false` |  |
| `labels` | map of string | no | `{}` |  |

Outputs: `name`, `self_link`, `url`

### `firewall`

Terraform/OpenTofu type: `google_compute_firewall`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `network` | string | yes | - | Name of a stack `network` resource. |
| `allow` | list of `AllowRule` | yes | - |  |
| `direction` | enum: `INGRESS`, `EGRESS` | no | `"INGRESS"` |  |
| `sourceRanges` | list of string | no | `[]` |  |
| `sourceTags` | list of string | no | `[]` |  |
| `targetTags` | list of string | no | `[]` |  |
| `destinationRanges` | list of string | no | `[]` |  |
| `priority` | integer (min 0, max 65535) | no | `1000` |  |

`AllowRule` object:

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `protocol` | string | no | `"tcp"` |  |
| `ports` | list of string | no | `[]` | e.g. ["22", "8000-8100"]; empty = all ports. |

Outputs: `id`, `self_link`

### `network`

Terraform/OpenTofu type: `google_compute_network`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `autoCreateSubnetworks` | boolean | no | `false` |  |
| `routingMode` | enum: `REGIONAL`, `GLOBAL` | no | `"REGIONAL"` |  |
| `description` | string | no | `""` |  |

Outputs: `id`, `name`, `self_link`

### `service_account`

Terraform/OpenTofu type: `google_service_account`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `accountId` | string | no | unset | 6-30 chars; default: resource name. |
| `displayName` | string | no | `""` |  |
| `description` | string | no | `""` |  |

Outputs: `email`, `id`, `name`

### `subnet`

Terraform/OpenTofu type: `google_compute_subnetwork`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `network` | string | yes | - | Name of a stack `network` resource. |
| `cidr` | string | yes | - |  |
| `region` | string | no | unset |  |
| `privateIpGoogleAccess` | boolean | no | `true` |  |

Outputs: `cidr`, `id`, `self_link`

### `vm`

Terraform/OpenTofu type: `google_compute_instance`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `machineType` | string | no | `"e2-small"` |  |
| `image` | string | no | `"debian-cloud/debian-12"` |  |
| `diskGb` | integer (min 10) | no | `20` |  |
| `zone` | string | no | unset |  |
| `subnet` | string | no | unset | Name of a stack `subnet` resource. |
| `network` | string | no | unset | Name of a stack `network` resource (default subnets). |
| `publicIp` | boolean | no | `false` |  |
| `tags` | list of string | no | `[]` |  |
| `labels` | map of string | no | `{}` |  |
| `metadata` | map of string | no | `{}` |  |
| `startupScript` | string | no | unset |  |
| `serviceAccount` | string | no | unset | Name of a stack `service_account` resource. |
| `serviceAccountEmail` | string | no | unset |  |
| `serviceAccountScopes` | list of string | no | `["https://www.googleapis.com/auth/cloud-platform"]` |  |
| `preemptible` | boolean | no | `false` |  |
| `spot` | boolean | no | `false` |  |

Outputs: `external_ip`, `id`, `internal_ip`, `self_link`


## Validation rules

- `vm` needs exactly one of `subnet` / `network`; at most one of `preemptible` / `spot`; at most one of `serviceAccount` / `serviceAccountEmail`.
- `firewall` with `direction: INGRESS` needs `sourceRanges` or `sourceTags`. With `EGRESS`, `destinationRanges` defaults to `0.0.0.0/0`.
- `subnet.cidr` must be a strict CIDR (no host bits); firewall ranges may be loose CIDRs.
- Service account ids (`accountId`, or the resource name) must be 6-30 chars of `[a-z0-9-]`, start with a letter.
- Bucket names (`bucketName`, or the resource name) must be valid GCS names and are globally unique.

## Outputs

Outputs listed under each resource type are returned by `apply` and `outputs` as `{resource-name: {key: value}}`, for example `iacforge outputs` prints `{"web": {"id": "...", "name": "web"}}`.

## Example

See [`examples/gcp/stack.yaml`](../../../examples/gcp/stack.yaml):

```yaml
# GCP network, subnet, firewall, VM, service account, bucket. Set providerConfig.project; uses ADC.
# bucket names are globally unique: change data-bucket-example-1.
apiVersion: iacforge/v1
kind: Stack
metadata:
  name: gcp-demo
spec:
  provider: gcp
  providerConfig:
    project: my-project
    labels:
      managed-by: iacforge
  resources:
  - name: sa
    type: service_account
    properties:
      accountId: app-runner
      displayName: App runner
  - name: vpc
    type: network
    properties: {}
  - name: subnet-a
    type: subnet
    properties:
      network: vpc
      cidr: 10.10.0.0/24
  - name: allow-ssh
    type: firewall
    properties:
      network: vpc
      allow:
      - protocol: tcp
        ports:
        - '22'
      sourceRanges:
      - 10.0.0.0/8
      targetTags:
      - ssh
  - name: web
    type: vm
    properties:
      subnet: subnet-a
      publicIp: true
      tags:
      - ssh
      serviceAccount: sa
      startupScript: '#!/bin/sh

        echo hi

        '
      metadata:
        role: web
      spot: true
  - name: data-bucket-example-1
    type: bucket
    properties:
      versioning: true
      location: US
```
