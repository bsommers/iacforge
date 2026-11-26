# Provider: gcp

| | |
|---|---|
| Status | beta |
| Category | cloud |
| Host platforms | darwin, linux, windows |
| Engines | opentofu, terraform, pulumi |
| Host tools | none (engine only) |
| Resource types | `artifact_registry`, `bucket`, `cloud_run_service`, `cloud_sql`, `firewall`, `gke_autopilot`, `iam_binding`, `network`, `secret`, `service_account`, `subnet`, `vm` |
| Upstream docs | <https://registry.terraform.io/providers/hashicorp/google/latest/docs> |

Google Cloud: VPC networks, subnets, firewalls, Compute Engine VMs, Cloud Storage buckets, service accounts, and (v0.2) Artifact Registry, Secret Manager, Cloud Run, GKE Autopilot, Cloud SQL and IAM bindings (`hashicorp/google ~> 6.0`; `pulumi-gcp` for Pulumi). **Status: beta**; promotion to stable is the v0.2 goal (see the [roadmap](../../ROADMAP.md)). The v0.2 resource types, remote state and import are in progress; see [gcp-plan.md](../../system/gcp-plan.md).

- Platforms: Linux, macOS, Windows. Engines: OpenTofu, Terraform, Pulumi.
- Host tools: none required by iacforge itself; install the `gcloud` CLI to authenticate.
- **Authentication:** never put credentials in a spec. Use Application Default Credentials:
  `gcloud auth application-default login` for a workstation, `GOOGLE_APPLICATION_CREDENTIALS` pointing to a key file for automation, or workload identity on GCP/CI. `providerConfig.project` is the only required setting.
- References: `subnet.network`, `firewall.network`, `vm.subnet`, `vm.network`, `vm.serviceAccount` name other stack resources and become implicit dependencies; iacforge checks the referenced resource has the right type.
- Planning and applying creates billable resources. Use `iacforge plan` first and `iacforge destroy` when done.

## Prerequisites

1. A GCP project with billing enabled, and `gcloud` installed.
2. Application Default Credentials: `gcloud auth application-default login` (workstation), `GOOGLE_APPLICATION_CREDENTIALS` (automation), or workload identity (CI, GCE, GKE). Credentials never go in the spec.
3. The Google APIs for the resources you use must be enabled in the project, either once by hand:

   ```sh
   gcloud services enable compute.googleapis.com storage.googleapis.com iam.googleapis.com \
     artifactregistry.googleapis.com secretmanager.googleapis.com run.googleapis.com \
     container.googleapis.com sqladmin.googleapis.com servicenetworking.googleapis.com \
     cloudresourcemanager.googleapis.com --project my-project
   ```

   or by setting `providerConfig.enableApis: true` (see below).
4. IAM roles for the identity running iacforge (grant only what the stack needs):

| Resource types | Roles |
|---|---|
| `network`, `subnet`, `firewall`, `vm` | `roles/compute.admin` (add `roles/iam.serviceAccountUser` to attach a service account to a VM) |
| `bucket` | `roles/storage.admin` |
| `service_account` | `roles/iam.serviceAccountAdmin` |
| `artifact_registry` | `roles/artifactregistry.admin` |
| `secret` | `roles/secretmanager.admin` |
| `cloud_run_service` | `roles/run.admin`, `roles/iam.serviceAccountUser` |
| `gke_autopilot` | `roles/container.admin` |
| `cloud_sql` | `roles/cloudsql.admin` (private IP also needs `roles/servicenetworking.networksAdmin`) |
| `iam_binding` | `roles/resourcemanager.projectIamAdmin` for project scope, or the resource's own admin role |
| `enableApis: true` | `roles/serviceusage.serviceUsageAdmin` |
| remote state | `roles/storage.objectUser` on the state bucket (see [state backends](../state-backends.md)) |

Run `iacforge schema gcp --json` for the machine-readable JSON Schema of everything below. Unknown keys are rejected, so typos fail at `validate`.

Property names are camelCase as written in the spec. Defaults shown as "unset" mean the property is omitted and the provider or engine default applies.

## providerConfig

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `project` | string (minLen 1) | yes | - | GCP project id (credentials come from ADC, never the spec). |
| `region` | string | no | `"us-central1"` |  |
| `zone` | string | no | `"us-central1-a"` |  |
| `labels` | map of string | no | `{}` | Default labels merged into labelled resources. |
| `enableApis` | boolean | no | `false` | Emit `google_project_service` helper blocks (`<name>_api`) for the APIs each resource needs, and make the resource depend on them. Off by default so iacforge does not change project-wide settings unasked. |

## Resource types

### `artifact_registry`

Terraform/OpenTofu type: `google_artifact_registry_repository`.

| Property | Description |
|---|---|
| `format` | `DOCKER`, `PYTHON`, ... |
| `location` | Registry location. |
| `description` | Free text. |
| `labels` | map of string |

Outputs: `id`, `name`, `repository_url`

### `secret`

Terraform/OpenTofu type: `google_secret_manager_secret`. Creates the container only; there is no value field.

| Property | Description |
|---|---|
| `replication` | `automatic` or user-managed regions. |
| `labels` | map of string |

Outputs: `id`, `secret_id`

Add the value out of band so it never enters the spec or state: `printf '%s' "$VALUE" | gcloud secrets versions add my-secret --data-file=-`.

### `cloud_run_service`

Terraform/OpenTofu type: `google_cloud_run_v2_service`.

| Property | Description |
|---|---|
| `image` | Container image (often an `artifact_registry` path). |
| `port` | Container port. |
| `env` | map of plain environment variables. |
| `secretEnv` | map of env var name -> name of a `secret` resource; rendered as a secret key reference. |
| `serviceAccount` | Name of a stack `service_account` resource. |
| `minInstances`, `maxInstances` | Scaling bounds. |
| `cpu`, `memory` | Resource limits. |
| `ingress` | Default: internal and load balancer only. |
| `allowUnauthenticated` | Default `false`. |
| `vpcConnector` | VPC access connector. |

Outputs: `id`, `uri`

### `gke_autopilot`

Terraform/OpenTofu type: `google_container_cluster` with `enable_autopilot = true`.

| Property | Description |
|---|---|
| `network`, `subnet` | Names of stack `network` / `subnet` resources. |
| `releaseChannel` | GKE release channel. |
| `privateNodes` | Default `true`. |
| `masterCidr` | Control-plane CIDR for private clusters. |
| `deletionProtection` | Default `true`; set `false` and apply before `destroy`. |

Outputs: `id`, `endpoint`, `name`

### `cloud_sql`

Terraform/OpenTofu type: `google_sql_database_instance`, plus a `google_sql_database` helper block `<name>_db`.

| Property | Description |
|---|---|
| `engine` | `POSTGRES_16`, `MYSQL_8_0`, ... |
| `tier` | Machine tier. |
| `diskGb` | Disk size. |
| `network` | Name of a stack `network` resource (private IP). |
| `availability` | Zonal or regional. |
| `backups` | Backup settings. |
| `databases` | List of database names. |
| `passwordSecret` | Name of a `secret` resource. Passwords are never accepted in the spec; prefer IAM database authentication. |
| `deletionProtection` | Default `true`; set `false` and apply before `destroy`. |

Outputs: `id`, `connection_name`, `private_ip`

### `iam_binding`

Terraform/OpenTofu type: `google_project_iam_member` or the matching `google_*_iam_member`.

| Property | Description |
|---|---|
| `role` | Role to grant, e.g. `roles/run.invoker`. |
| `member` | A literal like `user:me@example.com`, or the name of a `service_account` resource. |
| `scope` | Project (default) or the name of a bucket / secret / artifact registry resource. |

Outputs: `id`

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


## Safe defaults for the v0.2 types

- `cloud_run_service`: `allowUnauthenticated: false`, ingress limited to internal and load balancer traffic.
- `gke_autopilot`, `cloud_sql`: `deletionProtection: true`. `destroy` fails until you set it to `false` and apply that change.
- `gke_autopilot`: `privateNodes: true`.
- Secrets are references only. `secret` has no value field, `secretEnv` and `passwordSecret` point at `secret` resources, and the spec and state never hold secret material.
- References (`network`, `subnet`, `service_account`, `secret`, `artifact_registry`) become implicit dependencies and are type-checked.

## Related

- [State backends](../state-backends.md): keep state in a GCS bucket.
- [Importing existing resources](../import.md): adopt resources that already exist.

## Validation rules

- `vm` needs exactly one of `subnet` / `network`; at most one of `preemptible` / `spot`; at most one of `serviceAccount` / `serviceAccountEmail`.
- `firewall` with `direction: INGRESS` needs `sourceRanges` or `sourceTags`. With `EGRESS`, `destinationRanges` defaults to `0.0.0.0/0`.
- `subnet.cidr` must be a strict CIDR (no host bits); firewall ranges may be loose CIDRs.
- Service account ids (`accountId`, or the resource name) must be 6-30 chars of `[a-z0-9-]`, start with a letter.
- Bucket names (`bucketName`, or the resource name) must be valid GCS names and are globally unique.

## Outputs

Outputs listed under each resource type are returned by `apply` and `outputs` as `{resource-name: {key: value}}`, for example `iacforge outputs` prints `{"web": {"id": "...", "name": "web"}}`.

## Example

Also: [`examples/gcp/cloud-run/`](../../../examples/gcp/cloud-run/stack.yaml) (registry, secret, service account, Cloud Run, IAM) and [`examples/gcp/remote-state/`](../../../examples/gcp/remote-state/stack.yaml) (GCS backend).

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
