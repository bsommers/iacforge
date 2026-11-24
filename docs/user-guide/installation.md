# Installation

iacforge is a Python (>= 3.10) package. It does not bundle or download OpenTofu, Terraform, Pulumi or any provider tool: you install the ones you need. Run `iacforge doctor` at any point to see what it can find.

## 1. Install iacforge

Recommended: [uv](https://docs.astral.sh/uv/getting-started/installation/) (or [pipx](https://pipx.pypa.io/stable/installation/)).

```sh
uv tool install git+https://github.com/bsommers/iacforge
```

With extras (quote the argument):

```sh
uv tool install "iacforge[mcp] @ git+https://github.com/bsommers/iacforge"
uv tool install "iacforge[mcp,pulumi-docker] @ git+https://github.com/bsommers/iacforge"
```

| Extra | Adds | Needed for |
|---|---|---|
| `mcp` | `mcp>=1.2` | the `iacforge-mcp` server |
| `pulumi` | `pulumi>=3.100` | `engine: pulumi` with the `local` provider |
| `pulumi-docker` | `pulumi`, `pulumi-docker` | `engine: pulumi` with `docker` |
| `pulumi-libvirt` | `pulumi`, `pulumi-libvirt` | `engine: pulumi` with `libvirt` |
| `pulumi-gcp` | `pulumi`, `pulumi-gcp` | `engine: pulumi` with `gcp` |
| `pulumi-aws` | `pulumi`, `pulumi-aws` | `engine: pulumi` with `aws` |
| `dev` | `pytest`, `ruff` | working on iacforge itself |

Install scripts (install with `mcp`, via uv or pipx, then run `iacforge doctor`):

```sh
# Linux / macOS
sh scripts/install.sh
```

```powershell
# Windows (PowerShell)
.\scripts\install.ps1
```

Both honour `IACFORGE_REPO` to install from a different git URL or local path.

From a clone, for development:

```sh
git clone https://github.com/bsommers/iacforge
cd iacforge
uv venv && uv pip install -e ".[mcp,dev]"
.venv/bin/iacforge --help      # .venv\Scripts\iacforge on Windows
```

Check it works:

```sh
iacforge version
iacforge doctor
```

If `iacforge` is not found after `uv tool install`, run `uv tool update-shell` (or `pipx ensurepath`) and restart your shell.

## 2. Install an engine

You need at least one. OpenTofu is the default (`engine: opentofu`) and what the quickstarts use. If only `terraform` is installed, iacforge falls back to it (see [Engines](engines.md)).

The commands below are the upstream projects' standard install methods; see their docs if your platform differs.

### OpenTofu (<https://opentofu.org/docs/intro/install/>)

| OS | Command |
|---|---|
| Linux (snap) | `sudo snap install --classic opentofu` |
| Linux (other) | use the installer script or distro packages from the OpenTofu docs |
| macOS | `brew install opentofu` |
| Windows | `winget install --exact --id OpenTofu.Tofu` (or `choco install opentofu`) |

### Terraform (<https://developer.hashicorp.com/terraform/install>)

| OS | Command |
|---|---|
| Linux | add the HashiCorp apt/dnf repository, then `sudo apt install terraform` |
| macOS | `brew tap hashicorp/tap && brew install hashicorp/tap/terraform` |
| Windows | `winget install --exact --id Hashicorp.Terraform` |

### Pulumi (<https://www.pulumi.com/docs/install/>), only for `engine: pulumi`

| OS | Command |
|---|---|
| Linux / macOS | `curl -fsSL https://get.pulumi.com \| sh` or `brew install pulumi` |
| Windows | `winget install pulumi` |

Pulumi also needs the matching Python extra, for example `iacforge[pulumi-docker]`. Providers `hyperv` and `multipass` do not support Pulumi.

## 3. Install provider tools

| Provider | What the host needs |
|---|---|
| `local` | nothing beyond the engine |
| `docker` | a Docker-API daemon: Docker Desktop (macOS/Windows), Docker Engine (Linux), Colima, OrbStack, or rootless Podman through its socket. The `docker` CLI must be on `PATH` for `doctor` to report ready. |
| `libvirt` | Linux only: `virsh`, `qemu-img`, and a libvirt daemon (see below) |
| `multipass` | the `multipass` CLI (see below) |
| `hyperv` | Windows only: Hyper-V enabled, PowerShell, WinRM (see below) |
| `gcp` | credentials via Application Default Credentials; `gcloud` CLI recommended |
| `aws` | credentials via the standard AWS environment; `aws` CLI recommended |

### Docker

- Linux: install Docker Engine from <https://docs.docker.com/engine/install/> and add yourself to the `docker` group, or use rootless Podman and point `providerConfig.host` at `unix:///run/user/<uid>/podman/podman.sock` (`systemctl --user enable --now podman.socket`).
- macOS: Docker Desktop, Colima (`brew install colima docker`), or OrbStack.
- Windows: Docker Desktop. The daemon endpoint is `npipe:////./pipe/docker_engine`.

### libvirt (Linux)

Debian/Ubuntu:

```sh
sudo apt install qemu-kvm libvirt-daemon-system libvirt-clients qemu-utils
sudo usermod -aG libvirt "$USER"     # log out and back in
virsh -c qemu:///system list --all   # should print an empty table, not an error
```

Fedora: `sudo dnf install @virtualization`. The default `providerConfig.uri` is `qemu:///system`.

### Multipass (Linux, macOS, Windows)

- Linux: `sudo snap install multipass`
- macOS: `brew install --cask multipass`
- Windows: installer from <https://multipass.run/install>

### Hyper-V (Windows)

Enable the feature from an elevated PowerShell, then reboot:

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All
```

The provider talks to the host over WinRM (default `127.0.0.1:5986`, HTTPS, NTLM). Configure WinRM per the [taliesins/hyperv provider docs](https://registry.terraform.io/providers/taliesins/hyperv/latest/docs), run iacforge from an elevated session, and export credentials rather than writing them into the spec:

```powershell
$env:HYPERV_USER = "Administrator"
$env:HYPERV_PASSWORD = "..."
```

### GCP and AWS

Do not put credentials in a spec. Authenticate the shell instead:

```sh
gcloud auth application-default login     # GCP: Application Default Credentials
aws sso login --profile my-profile         # AWS: then set providerConfig.profile: my-profile
```

See the [gcp](providers/gcp.md) and [aws](providers/aws.md) pages.

## Verify

`iacforge doctor` prints host platform, which engines are present, and which providers are ready:

```
platform: linux
engines:
  opentofu   ok
  terraform  ok
  pulumi     missing
providers:
  docker     ready
  hyperv     not ready (unsupported on this OS)
  multipass  not ready (missing: multipass)
  ...
```

`iacforge --json doctor` returns the same data, plus the path of every tool found, for scripts and agents.
