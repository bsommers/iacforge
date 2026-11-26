# gcp cloud-run example

Artifact Registry repository, an empty Secret Manager secret, a service account, a private Cloud Run service reading the secret as `API_KEY`, and an IAM binding letting the service account read that secret. Set `providerConfig.project` and authenticate with `gcloud auth application-default login`. The sample image is Google's public hello container; push your own image to the registry and change `image` for real use.

```sh
iacforge validate stack.yaml
iacforge plan stack.yaml
iacforge apply stack.yaml --yes
# the secret has no value yet; add one out of band (never in the spec):
printf '%s' "s3cret" | gcloud secrets versions add api-key --data-file=- --project my-project
iacforge outputs stack.yaml
iacforge destroy stack.yaml --yes
```

The service is not publicly invokable (`allowUnauthenticated: false`). `enableApis: true` needs `roles/serviceusage.serviceUsageAdmin`; remove it if the APIs are already enabled. Creates billable resources.

Reference: [docs/user-guide/providers/gcp.md](../../../docs/user-guide/providers/gcp.md)
