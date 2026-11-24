# local example

Writes a file with the `local` provider. Needs only OpenTofu/Terraform. Run from a copy of this directory:

```sh
iacforge validate stack.yaml
iacforge plan stack.yaml
iacforge apply stack.yaml --yes
iacforge outputs stack.yaml
iacforge destroy stack.yaml --yes
```

Reference: [docs/user-guide/providers/local.md](../../docs/user-guide/providers/local.md)
