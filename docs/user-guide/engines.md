# Engines

An engine turns the validated spec into real infrastructure. Pick one with `spec.engine` or override per command with `--engine`.

| Engine | `spec.engine` | What iacforge writes | Needs |
|---|---|---|---|
| OpenTofu (default) | `opentofu` | `main.tf.json` | `tofu` (or `terraform`) |
| Terraform | `terraform` | `main.tf.json` | `terraform` (or `tofu`) |
| Pulumi | `pulumi` | a Python Pulumi project | `pulumi` CLI, `pulumi` Python SDK + provider package |

Provider support: all providers support OpenTofu/Terraform. Pulumi is supported by `local`, `docker`, `libvirt`, `gcp` and `aws`; `hyperv` and `multipass` are OpenTofu/Terraform only (`validate` fails with `unsupported`).

## OpenTofu and Terraform

Both engines render the same `main.tf.json` (Terraform's JSON syntax, deterministic, sorted keys) and drive the binary with `init`, `plan`, `apply -auto-approve`, `destroy -auto-approve` and `output -json`, always with `-input=false -no-color`, and `TF_IN_AUTOMATION=1`, `CHECKPOINT_DISABLE=1`. A command times out after one hour.

### Binary selection

1. If `IACFORGE_TF_BINARY` is set (a name on `PATH` or a full path), only that is tried.
2. Otherwise `engine: opentofu` looks for `tofu` then `terraform`; `engine: terraform` looks for `terraform` then `tofu`.
3. If nothing is found: `tool_missing` (exit 3).

```sh
IACFORGE_TF_BINARY=/opt/terraform/1.9/terraform iacforge plan
```

`iacforge doctor` reports `terraform ok` when either binary exists, because of the fallback.

### State

State is Terraform's default local backend: `terraform.tfstate` inside the workdir (`.iacforge/<stack>/<engine>/`). The state of an `opentofu` run and a `terraform` run of the same stack live in different directories. Provider plugins are downloaded by `init` from the registry, so the first `plan` needs network access.

`init` is skipped on later runs when `main.tf.json` and the lock file are unchanged.

### Provider versions

Pinned in the rendered config (`required_providers`): for example `hashicorp/local ~> 2.5`, `kreuzwerker/docker ~> 3.0`, `dmacvicar/libvirt ~> 0.8.1`, `hashicorp/google ~> 6.0`, `hashicorp/aws ~> 5.0`, `larstobi/multipass ~> 1.4`.

## Pulumi

```sh
uv tool install "iacforge[pulumi-docker] @ git+https://github.com/bsommers/iacforge"   # docker + pulumi
iacforge plan --engine pulumi
```

- **Backend:** a local file backend at `file://<workdir>/state`. No Pulumi Cloud account or login is needed.
- **Secrets passphrase:** `PULUMI_CONFIG_PASSPHRASE` if set, otherwise the empty string. That is fine for throwaway local state; set it explicitly if the stack holds real secrets and you keep the state:

  ```sh
  export PULUMI_CONFIG_PASSPHRASE='a long passphrase'
  ```

  Use the same passphrase for every later command on that stack.
- The program runs in-process through the Pulumi Automation API with the workdir as current directory, so relative paths behave as with OpenTofu.
- Project name is `iacforge`; the Pulumi stack is named after `metadata.name`.
- `plan` under Pulumi reports counts but an empty `resources` list.
- Missing pieces fail with `tool_missing` and a hint: the `pulumi` CLI, or the Python SDK (`pip install 'iacforge[pulumi]'`) and the provider package (extras `pulumi-docker`, `pulumi-libvirt`, `pulumi-gcp`, `pulumi-aws`).

## Ejecting the rendered project

`iacforge render` writes engine-native files without running anything, so you can leave iacforge at any point or inspect exactly what will run.

OpenTofu/Terraform:

```sh
iacforge render --workdir ./eject
cd eject
tofu init && tofu plan          # or terraform
```

`main.tf.json` is standard Terraform JSON; no iacforge needed to run it. Note that output names are flattened as `<resource>__<key>`.

Pulumi:

```sh
iacforge render --engine pulumi --workdir ./eject
ls eject      # Pulumi.yaml  __main__.py  requirements.txt  stack.json
```

`Pulumi.yaml` points at the file backend (`file://./state`), `stack.json` is the stack spec, and `__main__.py` loads it and runs the same program the engine runs. The ejected project still imports `iacforge` (see `requirements.txt`), so install it in the Pulumi project's Python environment before `pulumi up`; it is not a standalone port of your infrastructure.

## Choosing

- Start with OpenTofu: fewest moving parts, supports every provider, open-source licence.
- Use `terraform` if your organisation standardises on HashiCorp's binary.
- Use `pulumi` if you want a Pulumi state and tooling (stack outputs, `pulumi` CLI) and the provider supports it.
