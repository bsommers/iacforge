# hyperv example

Hyper-V switch, VHD and VM (Windows, elevated). Export `HYPERV_USER` and `HYPERV_PASSWORD` first.

```sh
iacforge validate stack.yaml
iacforge plan stack.yaml
iacforge apply stack.yaml --yes
iacforge outputs stack.yaml
iacforge destroy stack.yaml --yes
```

Reference: [docs/user-guide/providers/hyperv.md](../../docs/user-guide/providers/hyperv.md)
