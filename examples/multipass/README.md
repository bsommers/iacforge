# multipass example

Ubuntu 24.04 VM with a cloud-init package list. Needs the `multipass` CLI.

```sh
iacforge validate stack.yaml
iacforge plan stack.yaml
iacforge apply stack.yaml --yes
iacforge outputs stack.yaml
iacforge destroy stack.yaml --yes
```

Reference: [docs/user-guide/providers/multipass.md](../../docs/user-guide/providers/multipass.md)
