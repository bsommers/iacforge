# docker example

nginx container on port 8089 with a network, volume and image. Needs a running Docker daemon.

```sh
iacforge validate stack.yaml
iacforge plan stack.yaml
iacforge apply stack.yaml --yes
iacforge outputs stack.yaml
iacforge destroy stack.yaml --yes
```

Reference: [docs/user-guide/providers/docker.md](../../docs/user-guide/providers/docker.md)
