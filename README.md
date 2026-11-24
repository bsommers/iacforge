# iacforge

Provider-neutral infrastructure provisioning for humans, AI agents and code. Write one YAML stack spec; iacforge validates it, renders it to OpenTofu/Terraform JSON or a Pulumi program, and runs the engine for you.

- **One spec, many targets:** local files, Docker, libvirt/KVM, Hyper-V, Multipass, GCP (beta) and AWS (scaffold).
- **One spec, many engines:** OpenTofu (default), Terraform or Pulumi, switchable per run. `iacforge render` lets you eject the generated project at any time.
- **Three uniform surfaces:** a CLI with a stable `--json` envelope and exit codes, a Python API (`iacforge.core`), and an MCP server (`iacforge-mcp`) for AI agents.
- **Safe by default:** strict validation (unknown keys are errors), no credentials in specs, and `apply`/`destroy` refuse to run without explicit confirmation.

## Feature matrix

Generated from `iacforge providers --json`.

| Provider | Status | Host OS | Engines | Resource types | Host tools |
|---|---|---|---|---|---|
| [`aws`](docs/user-guide/providers/aws.md) | scaffold | darwin, linux, windows | opentofu, terraform, pulumi | bucket, security_group, subnet, vm, vpc | - |
| [`docker`](docs/user-guide/providers/docker.md) | stable | darwin, linux, windows | opentofu, terraform, pulumi | container, image, network, volume | docker |
| [`gcp`](docs/user-guide/providers/gcp.md) | beta | darwin, linux, windows | opentofu, terraform, pulumi | bucket, firewall, network, service_account, subnet, vm | - |
| [`hyperv`](docs/user-guide/providers/hyperv.md) | beta | windows | opentofu, terraform | switch, vhd, vm | powershell |
| [`libvirt`](docs/user-guide/providers/libvirt.md) | beta | linux | opentofu, terraform, pulumi | network, pool, vm, volume | virsh, qemu-img |
| [`local`](docs/user-guide/providers/local.md) | stable | darwin, linux, windows | opentofu, terraform, pulumi | file | - |
| [`multipass`](docs/user-guide/providers/multipass.md) | beta | darwin, linux, windows | opentofu, terraform | vm | multipass |

Status: `stable` is exercised end to end; `beta` is implemented and unit tested; `scaffold` renders but has not been run against a live account. Pulumi additionally needs the matching extra (for example `iacforge[pulumi-docker]`). Run `iacforge doctor` to see which providers are ready on your machine.

## Install

```sh
uv tool install git+https://github.com/bsommers/iacforge
uv tool install "iacforge[mcp] @ git+https://github.com/bsommers/iacforge"   # with the MCP server
uv tool install "iacforge[mcp,pulumi-docker] @ git+https://github.com/bsommers/iacforge"
```

Extras: `mcp`, `pulumi`, `pulumi-docker`, `pulumi-libvirt`, `pulumi-gcp`, `pulumi-aws`, `dev`. Or run `scripts/install.sh` (Linux/macOS) / `scripts\install.ps1` (Windows). You also need an engine: install [OpenTofu](https://opentofu.org/docs/intro/install/) (or Terraform, or Pulumi). iacforge never downloads engines. Details: [installation guide](docs/user-guide/installation.md).

## Quickstart: 60 seconds, `local` provider

```sh
mkdir iacforge-demo && cd iacforge-demo
iacforge init                 # writes stack.yaml
iacforge validate             # valid: stack 'dev' provider=local engine=opentofu resources=1
iacforge plan                 # plan: +1 ~0 -0
iacforge apply --yes          # apply: +1 ~0 -0, prints outputs
iacforge outputs
iacforge destroy --yes        # destroy: +0 ~0 -1
```

The file is created at `.iacforge/dev/opentofu/out/hello.txt` (relative paths resolve inside the stack's working directory). Without `--yes`, `apply` and `destroy` refuse to run non-interactively (exit code 5).

## Docker quickstart

Needs a running Docker daemon.

```sh
cp examples/docker/stack.yaml .
iacforge validate && iacforge plan
iacforge apply --yes
curl -I http://localhost:8089        # nginx
iacforge destroy --yes
```

A stack spec looks like this:

```yaml
apiVersion: iacforge/v1
kind: Stack
metadata:
  name: web
spec:
  provider: docker
  engine: opentofu            # opentofu | terraform | pulumi
  resources:
    - name: net
      type: network
    - name: web
      type: container
      properties:
        image: nginx:1.27-alpine
        ports: [{internal: 80, external: 8089}]
        networks: [net]       # implicit dependency on `net`
```

## Use it from agents and code

```sh
iacforge --json plan          # {"ok": true, "command": "plan", "data": {...}}
claude mcp add iacforge -- iacforge-mcp
```

```python
from iacforge import core
core.plan("stack.yaml")
core.apply("stack.yaml", confirm=True)
```

## Documentation

- User guide: [index](docs/user-guide/index.md), [installation](docs/user-guide/installation.md), [quickstart](docs/user-guide/quickstart.md), [stack spec](docs/user-guide/stack-spec.md), [CLI reference](docs/user-guide/cli-reference.md), [engines](docs/user-guide/engines.md), [MCP](docs/user-guide/mcp.md), [troubleshooting](docs/user-guide/troubleshooting.md), [FAQ](docs/user-guide/faq.md)
- Providers: [local](docs/user-guide/providers/local.md), [docker](docs/user-guide/providers/docker.md), [libvirt](docs/user-guide/providers/libvirt.md), [hyperv](docs/user-guide/providers/hyperv.md), [multipass](docs/user-guide/providers/multipass.md), [gcp](docs/user-guide/providers/gcp.md), [aws](docs/user-guide/providers/aws.md)
- Examples: [`examples/`](examples/), one runnable stack per provider
- Architecture: [docs/architecture.md](docs/architecture.md), [docs/system/](docs/system/contracts.md)
- AI agents: [AGENTS.md](AGENTS.md), [docs/agents/](docs/agents/using-iacforge.md)
- Project: [ROADMAP](docs/ROADMAP.md), [ADRs](docs/adr/), [CONTRIBUTING.md](CONTRIBUTING.md)

## License

Apache-2.0. See [LICENSE](LICENSE).
