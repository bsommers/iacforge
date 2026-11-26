# GCP first-class: design for v0.2

Status: **in progress (v0.2)**, consistent with [ROADMAP.md](../ROADMAP.md). Sections 1, 2 and 4
are being implemented (see ADR 0005 and 0006); sections 3 and 5 are not started. Each item names the files that change. Contract changes
get an ADR (0005+).

## Current state (beta)

`adapters/gcp.py` (`status = "beta"`, both engines) supports `network`, `subnet`, `firewall`, `vm`,
`bucket`, `service_account` on `hashicorp/google ~> 6.0` / `pulumi-gcp>=7.0`. `providerConfig`:
`project`, `region`, `zone`, default `labels`. Credentials come from Application Default
Credentials only. Unit tests (`tests/test_adapter_gcp.py`) render and validate; no live test
runs against a real project. State is local in the workdir. There is no import and no policy layer.

## Goals

1. Real resources people deploy on GCP: serverless, Kubernetes, databases, registry, secrets, IAM.
2. Safe shared state: GCS remote backend for both engines.
3. Proven by live end-to-end tests in a sandbox project with keyless CI auth.
4. Adopt existing infrastructure: `iacforge import`.
5. Promote `gcp` from `beta` to `stable`.

Non-goals for v0.2: multi-provider stacks, policy hooks, drift (all v0.3).

## 1. New resource types

Same adapter conventions as existing types (strict models, `references()` + `validate_stack()`,
output keys, `tf_types` + `pulumi_resource`, an entry in `EXAMPLES` so the contract suite covers
them). Terraform types are the `hashicorp/google` resources.

| type | Terraform resource | Key properties (camelCase) | Outputs |
|---|---|---|---|
| `artifact_registry` | `google_artifact_registry_repository` | `format` (DOCKER, PYTHON, ...), `location`, `description`, `labels` | `id`, `name`, `repository_url` (computed) |
| `secret` | `google_secret_manager_secret` | `replication` (automatic or user-managed regions), `labels`; **no value field** | `id`, `secret_id` |
| `cloud_run_service` | `google_cloud_run_v2_service` | `image`, `port`, `env`, `secretEnv` (name -> `secret` resource), `serviceAccount`, `minInstances`, `maxInstances`, `cpu`, `memory`, `ingress`, `allowUnauthenticated`, `vpcConnector` | `id`, `uri` |
| `gke_autopilot` | `google_container_cluster` (`enable_autopilot = true`) | `network`, `subnet`, `releaseChannel`, `privateNodes`, `masterCidr`, `deletionProtection` | `id`, `endpoint`, `name` |
| `cloud_sql` | `google_sql_database_instance` (+ `google_sql_database`, helper block `<id>_db`) | `engine` (POSTGRES_16, MYSQL_8_0), `tier`, `diskGb`, `network` (private IP), `availability`, `backups`, `databases`, `deletionProtection` | `id`, `connection_name`, `private_ip` |
| `iam_binding` | `google_project_iam_member` / `google_*_iam_member` | `role`, `member` (a literal `user:...` or a `service_account` resource), `scope` (project or a bucket/secret/registry resource) | `id` |

Design rules specific to these:

- **Secrets are references only.** `secret` creates the container; values are added out of band
  (`gcloud secrets versions add`). Cloud Run's `secretEnv` maps an environment variable to a
  `secret` resource and renders a `value_source.secret_key_ref`. The spec and state therefore never
  hold secret material. Cloud SQL passwords are not accepted in the spec; the adapter will support
  `passwordSecret: <secret resource>` and document using IAM database authentication.
- **Safe defaults.** `deletionProtection: true` for `gke_autopilot` and `cloud_sql` (overridable,
  required to be `false` before `destroy` works), `ingress` defaults to internal-and-load-balancer
  for Cloud Run, `allowUnauthenticated` defaults to `false`, `privateNodes` defaults to `true`.
- **Dependencies.** `references()` returns the names of `network`, `subnet`, `service_account`,
  `secret`, `artifact_registry` referenced from properties; `validate_stack()` rejects wrong-type
  references (pattern already used in `GcpAdapter.validate_stack`).
- **API enablement.** Resources need their Google APIs enabled. The adapter will add an optional
  `providerConfig.enableApis: bool` (default false) that emits `google_project_service` helper
  blocks named `<tf_id(name)>_api` and adds them to `depends_on`; the default avoids surprising
  project-wide changes and makes the missing-API failure explicit in `doctor`-style hints.
- **Naming.** Helper blocks follow `<tf_id(name)>_<suffix>`; outputs keep the flat/nest convention.
- **Pulumi parity** via `pulumi_gcp` (`cloudrunv2.Service`, `container.Cluster`, `sql.DatabaseInstance`,
  `artifactregistry.Repository`, `secretmanager.Secret`, `projects.IAMMember`).

## 2. Remote state on GCS

New optional spec section (generic, so a later AWS S3 backend fits the same shape):

```yaml
spec:
  provider: gcp
  providerConfig: {project: my-proj}
  backend:
    type: gcs
    bucket: my-proj-iacforge-state
    prefix: stacks            # state key: <prefix>/<stack name>[/<engine>]
```

Implementation sketch:

- `spec.py`: add `Backend` model (`extra="forbid"`; `type: Literal["local","gcs"]`, default local) to
  `StackBody`; `render.BoundStack` carries it; adapters declare `backends: ClassVar[frozenset[str]]`
  (gcp: `{"gcs", "local"}`) validated in `bind()` (error: `unsupported`).
- **Terraform**: `render_terraform` adds `terraform.backend.gcs = {bucket, prefix}` to the document.
  The engine's `_init` already re-runs `init` whenever `main.tf.json` changes (its stamp is the
  config hash); on a backend change it must pass `-migrate-state -force-copy` only when the user asks, otherwise
  `-reconfigure`. The workdir keeps no `terraform.tfstate`.
- **Pulumi**: `PulumiEngine._env` / `_open_stack` use `PULUMI_BACKEND_URL=gs://<bucket>/<prefix>` instead
  of `file://<workdir>/state`; the ejected `Pulumi.yaml` gets the same `backend.url`.
  A real `PULUMI_CONFIG_PASSPHRASE` (or a KMS secrets provider) becomes mandatory with a remote
  backend: `bind()` should error if it is unset.
- **Bootstrapping**: the state bucket is not created by the stack it stores. `iacforge init
  --provider gcp --with-state-bucket` (or a documented one-off `gcloud storage buckets create ...
  --uniform-bucket-level-access --public-access-prevention`) creates it with versioning on. Locking
  is provided by GCS object generation (Terraform) and the Pulumi gs backend.
- **Security**: access controlled by IAM on the bucket (`roles/storage.objectUser` for CI);
  state still contains secrets (see [security.md](security.md)); enable bucket versioning and CMEK
  where required.
- Tests: fake-runner tests assert the backend block and the init sequence; the live job (below)
  proves round-trip with a real bucket.

## 3. CI end-to-end with Workload Identity Federation

An **opt-in** workflow (`.github/workflows/e2e-gcp.yml`, trigger `workflow_dispatch` plus a label
on trusted PRs; never for forks) so ordinary CI stays offline and free.

Auth: no long-lived keys. A Workload Identity Pool + OIDC provider trusts GitHub's token issuer
with an attribute condition pinning the repository (`assertion.repository == 'bsommers/iacforge'`)
and branch/environment; a dedicated service account in a sandbox project is impersonated by
`google-github-actions/auth` (pinned by SHA like other actions). Workflow `permissions:` is
`contents: read` and `id-token: write` on that job only; `persist-credentials: false`.

Sandbox hygiene:

- A dedicated GCP project with a budget alert and org-policy limits; the CI service account has
  only the roles the tests need (`compute.admin` scoped by a name-prefix IAM condition,
  `storage.admin`, `iam.serviceAccountAdmin`, ...).
- Every test stack uses a unique run-scoped name (`iacforge-e2e-<run id>`), labels
  `managed-by=iacforge,e2e=true`, and ends in `destroy` inside `finally` (same pattern as the live
  Docker test).
- A scheduled janitor job deletes resources labelled `e2e=true` older than 24 h.
- Tests carry a new marker `gcp` (declared in `pyproject.toml`) and skip unless
  `IACFORGE_E2E_GCP_PROJECT` is set, so local runs and fork PRs are unaffected.

Test matrix: network + subnet + firewall + bucket + service account (cheap, fast) on both
`opentofu` and `pulumi`; Cloud Run + Artifact Registry (public sample image) once per release;
GKE and Cloud SQL only in a manual, nightly or pre-release job because of cost and duration. Each
live test asserts `plan` shows zero changes after `apply` (idempotence).

## 4. `iacforge import`

Adopt existing resources into state and (best effort) into a spec.

New core operation `import_resource` exposed as CLI `iacforge import`, MCP `iacforge_import`, entry
in `surfaces.OPERATIONS` (parity test enforces it). It is a mutating operation: gated by
`confirm`, since it writes state.

```
iacforge import stack.yaml --resource web --id projects/p/zones/z/instances/web --yes
```

- Terraform engine: `tofu import <address> <id>` where the address is
  `<tf_types[type]>.<tf_id(name)>`; the spec must already declare the resource (the adapter's
  strict validation then tells the user which properties to fill in). Terraform >= 1.5 `import`
  blocks are also viable and render deterministically into `main.tf.json`.
- Pulumi engine: `stack.import_resources` / `pulumi import` with the logical name = stack resource
  name.
- Adapter hook (additive, optional): `import_id(res, props, config) -> str` building the provider's
  ID format (e.g. `projects/{project}/zones/{zone}/instances/{name}`); default raises
  `UnsupportedError`. A read-only discovery command (`iacforge import --discover <type>`) that emits
  a draft spec via `gcloud`/API listing is a stretch goal.
- Safety: always followed by `plan`; the result envelope reports `imported: true` and the plan
  diff so the user sees what a first `apply` would change.

## 5. Promotion criteria (beta -> stable)

- All table types implemented on both engines, covered by contract + provider tests.
- Live e2e green for the cheap matrix on both engines for two consecutive releases.
- GCS backend and import documented and tested.
- Provider page in docs with prerequisites (APIs, IAM roles, WIF setup).

## Work breakdown

1. Backend model + Terraform/Pulumi backend plumbing (+ ADR for the `spec.backend` contract).
2. New resource types in vertical slices (registry + secret + IAM first, then Cloud Run, Cloud SQL,
   GKE).
3. Live e2e job and sandbox project; add `gcp` marker.
4. `import` operation and adapter hook (+ ADR for the contract addition).
5. Docs page, roadmap update, status -> stable.
