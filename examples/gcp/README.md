# gcp example

VPC, subnet, firewall, spot VM, service account and bucket. Set `providerConfig.project`, change the globally unique bucket name, authenticate with `gcloud auth application-default login`. Creates billable resources.

```sh
iacforge validate stack.yaml
iacforge plan stack.yaml
iacforge apply stack.yaml --yes
iacforge outputs stack.yaml
iacforge destroy stack.yaml --yes
```

Reference: [docs/user-guide/providers/gcp.md](../../docs/user-guide/providers/gcp.md)
