# gcp remote-state example

A network, subnet and bucket whose state is stored in GCS at `gs://<bucket>/iacforge/remote-state-demo/opentofu`.

Create the state bucket once (iacforge does not):

```sh
gcloud storage buckets create gs://my-project-iacforge-state --project my-project \
  --location us-central1 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://my-project-iacforge-state --versioning
```

Then set `providerConfig.project`, `backend.bucket` and the globally unique data bucket name:

```sh
iacforge validate stack.yaml
iacforge plan stack.yaml
iacforge apply stack.yaml --yes
iacforge destroy stack.yaml --yes
```

With `--engine pulumi`, set a non-empty `PULUMI_CONFIG_PASSPHRASE` first. Details: [docs/user-guide/state-backends.md](../../../docs/user-guide/state-backends.md)
