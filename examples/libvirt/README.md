# libvirt example

KVM VM on a NAT network (Linux with libvirt). Replace the placeholder SSH key first.

```sh
iacforge validate stack.yaml
iacforge plan stack.yaml
iacforge apply stack.yaml --yes
iacforge outputs stack.yaml
iacforge destroy stack.yaml --yes
```

Reference: [docs/user-guide/providers/libvirt.md](../../docs/user-guide/providers/libvirt.md)
