# State backends

State records which real resources a stack owns. By default it is local; with `spec.backend` it lives in a GCS bucket so it can be shared, locked and recovered. Contract: [ADR 0005](../adr/0005-spec-backend.md).

## Local vs gcs

| | `local` (default) | `gcs` |
|---|---|---|
| State location | the workdir `.iacforge/<stack>/<engine>/` | `gs://<bucket>/<prefix>/<stack>/<engine>` |
| Sharing | one machine | anyone with bucket access |
| Locking | none | Terraform/OpenTofu: GCS object generation; Pulumi: the `gs://` backend |
| Providers | all | `gcp` only |
| Extra requirement | none | ADC with access to the bucket; Pulumi needs `PULUMI_CONFIG_PASSPHRASE` |

Omitting `backend` is the same as `{type: local}`; existing specs are unchanged.

## Spec

```yaml
spec:
  provider: gcp
  providerConfig: {project: my-project}
  backend:
    type: gcs
    bucket: my-project-iacforge-state   # required for gcs, not allowed for local
    prefix: iacforge                    # optional, default "iacforge"
```

There are no credentials in `backend`. Access comes from ADC, the same as the provider. A provider that does not support the backend type fails `validate` with code `unsupported`.

## State key

`<prefix>/<stack name>/<engine>`, for example `iacforge/gcp-demo/opentofu`. Each engine has its own object, so switching `spec.engine` starts from empty state instead of corrupting the other engine's. The last segment is the value of `spec.engine`; destroy with the original engine before switching.

## Bootstrap the bucket

iacforge never creates the bucket that stores a stack's own state. Create it once, by hand:

```sh
gcloud storage buckets create gs://my-project-iacforge-state \
  --project my-project --location us-central1 \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://my-project-iacforge-state --versioning
gcloud storage buckets add-iam-policy-binding gs://my-project-iacforge-state \
  --member user:me@example.com --role roles/storage.objectUser
```

- Versioning lets you recover a deleted or corrupted state object.
- Uniform access and public access prevention keep the bucket private and IAM-only.
- State contains secrets in clear text: grant `roles/storage.objectUser` only to people and CI identities that may apply the stack, and consider CMEK. See [security](../system/security.md).

## Pulumi passphrase

With a remote backend, iacforge refuses to run the Pulumi engine unless `PULUMI_CONFIG_PASSPHRASE` is set and non-empty (error before any state is touched). The empty-passphrase dev default is not acceptable for shared state.

```sh
export PULUMI_CONFIG_PASSPHRASE="$(cat ~/.config/iacforge/passphrase)"
iacforge plan stack.yaml --engine pulumi
```

Everyone who uses the stack needs the same passphrase.

## Changing backends: no implicit migration

Adding, removing or editing `backend` makes the next run re-initialise the engine with `-reconfigure`. iacforge never copies state between backends for you, so after switching the new backend starts empty and `plan` will propose to create everything that already exists.

To move existing state, do it explicitly with the engine tool before applying:

- Terraform/OpenTofu: `cd .iacforge/<stack>/<engine> && tofu init -migrate-state -force-copy`, or `tofu state pull > backup.tfstate` first.
- Pulumi: `pulumi stack export` from the old backend and `pulumi stack import` into the new one.

Alternatively, [import](import.md) the resources into the new backend.

## Files in the workdir

With `type: gcs` the workdir holds rendered files and the provider cache but no `terraform.tfstate`/`state/`. Run `iacforge render` to see the backend block in `main.tf.json`.
