# Quickstart

You need iacforge and OpenTofu (or Terraform) installed: see [Installation](installation.md). The first quickstart uses the `local` provider, which only writes a file, so it is safe to run anywhere.

## 60 seconds with the `local` provider

```sh
mkdir iacforge-demo && cd iacforge-demo

iacforge init                 # writes stack.yaml (provider local, engine opentofu)
iacforge validate
iacforge plan
iacforge apply --yes
iacforge outputs
iacforge destroy --yes
```

Real output from those commands:

```
$ iacforge init
wrote stack.yaml
$ iacforge validate
valid: stack 'dev' provider=local engine=opentofu resources=1
$ iacforge plan
plan: +1 ~0 -0
$ iacforge apply --yes
apply: +1 ~0 -0
outputs:
{
  "hello": {
    "id": "2c1a559b8b8f5549590d6e8434bc61148f73b080",
    "path": "out/hello.txt"
  }
}
$ iacforge outputs
{
  "hello": {
    "id": "2c1a559b8b8f5549590d6e8434bc61148f73b080",
    "path": "out/hello.txt"
  }
}
$ iacforge destroy --yes
destroy: +0 ~0 -1
```

(`destroy` prints its counts in the same `+add ~change -destroy` format, so a destroy of one resource shows `-1`.)

What happened:

- `init` wrote this `stack.yaml`:

  ```yaml
  apiVersion: iacforge/v1
  kind: Stack
  metadata:
    name: dev
  spec:
    provider: local
    engine: opentofu
    providerConfig: {}
    resources:
    - name: hello
      type: file
      properties:
        path: out/hello.txt
        content: 'hello from iacforge

          '
  ```

- `validate` checked it against the `local` provider's schema without touching anything.
- `plan` rendered `.iacforge/dev/opentofu/main.tf.json`, ran `tofu init` and `tofu plan`, and reported `+1` resource to add.
- `apply --yes` created the file. Relative paths resolve against the working directory, so it is at `.iacforge/dev/opentofu/out/hello.txt`. Without `--yes`, `apply` and `destroy` refuse to run non-interactively (exit code 5).
- `destroy --yes` removed it. State (`terraform.tfstate`) stays in the workdir.

Machine-readable mode: put `--json` **before** the command.

```sh
iacforge --json plan
```

```json
{"command": "plan", "data": {"changes": {"add": 0, "change": 0, "destroy": 0}, "engine": "opentofu", "has_changes": false, "provider": "local", "resources": [], "stack": "dev", "workdir": ".../.iacforge/dev/opentofu", "log": "..."}, "ok": true}
```

Peek at what iacforge generates without running the engine:

```sh
iacforge render --workdir ./eject
cat eject/main.tf.json
```

## Docker quickstart

Needs a running Docker daemon. This is the shipped [`examples/docker/stack.yaml`](../../examples/docker/stack.yaml): a network, a volume, an image and an nginx container published on port 8089.

```sh
cp examples/docker/stack.yaml .       # from a clone of the repo
iacforge validate
iacforge plan                         # plan: +4 ~0 -0
iacforge apply --yes
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8089     # 200
iacforge outputs                      # ids, names and the container IP
iacforge destroy --yes
```

Or start from a generated spec:

```sh
iacforge init --provider docker --name web
```

That writes a smaller starter: one network plus `nginx:1.27-alpine` on host port 8080. If port 8080 is in use, edit `ports[].external`.

If `apply` fails with `Pool overlaps with other one on this address space`, the `subnet` you set on a docker `network` collides with an existing network. Omit `subnet` or pick another range.

## Other providers

Each provider has a runnable example under [`examples/`](../../examples/) and a reference page:

| Provider | Example | Reference |
|---|---|---|
| local | [examples/local](../../examples/local/) | [local](providers/local.md) |
| docker | [examples/docker](../../examples/docker/) | [docker](providers/docker.md) |
| libvirt (Linux) | [examples/libvirt](../../examples/libvirt/) | [libvirt](providers/libvirt.md) |
| hyperv (Windows) | [examples/hyperv](../../examples/hyperv/) | [hyperv](providers/hyperv.md) |
| multipass | [examples/multipass](../../examples/multipass/) | [multipass](providers/multipass.md) |
| gcp (beta) | [examples/gcp](../../examples/gcp/) | [gcp](providers/gcp.md) |
| aws (scaffold) | [examples/aws](../../examples/aws/) | [aws](providers/aws.md) |

Always `validate` and `plan` before `apply`, especially for the cloud providers, which create billable resources.

## From Python

```python
from iacforge import core

core.validate("stack.yaml")
print(core.plan("stack.yaml")["changes"])
print(core.apply("stack.yaml", confirm=True)["outputs"])
core.destroy("stack.yaml", confirm=True)
```

Every function returns a dict (the `data` part of the CLI envelope) and raises a subclass of `iacforge.errors.IacForgeError` carrying `.code` and `.exit_code`. `spec` may be a path, inline YAML/JSON text, a dict or a parsed `StackSpec`.
