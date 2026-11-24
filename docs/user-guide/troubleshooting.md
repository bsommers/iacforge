# Troubleshooting

Start with `iacforge doctor` (human) or `iacforge --json doctor` (paths of every tool found, per-provider `ready`, `missing_tools`). Then match the error code below. Every failure prints `error[<code>]: <message>` on stderr (or the JSON envelope with `--json`).

## By error code

### `invalid_spec` (exit 2)

The spec failed validation. Details list a `path` and message per problem; fix them all, then re-run `validate`.

| Message | Cause |
|---|---|
| `metadata.name: String should match pattern ...` | Stack and resource names must match `^[a-z][a-z0-9-]{0,62}$` (lowercase, digits, hyphens, start with a letter). |
| `<key>: Extra inputs are not permitted` | A typo or unknown field. Unknown keys are rejected at every level. Check spelling and camelCase (`dependsOn`, `providerConfig`, `memoryMb`). |
| `apiVersion: Field required` | The file is not a stack spec, or is missing `apiVersion: iacforge/v1`, `kind: Stack`, `metadata`, `spec`. |
| `dependency cycle: a -> b -> a` | `dependsOn` (or implicit references) form a loop. |
| `a: 'b' is a volume, expected a network resource` | A property that names another resource points at the wrong type. |
| `provider 'local' has no resource type 'bucket'` | Wrong `type` for the provider. `iacforge providers <name>` lists the valid ones. |
| `exactly one of 'image' or 'imageFrom' is required` | docker container: set one, not both. |
| `cannot read spec file ...` | Path wrong. The default is `./stack.yaml`; pass the path or `-` for stdin. |
| `... already exists (use force/--force to overwrite)` | `init` refuses to overwrite. |

### `unknown_provider` (exit 2)

`details.known` lists valid names: `aws`, `docker`, `gcp`, `hyperv`, `libvirt`, `local`, `multipass`.

### `unsupported` (exit 2)

The provider does not offer that engine (for example `engine: pulumi` with `hyperv` or `multipass`). Use `--engine opentofu`.

### `tool_missing` (exit 3)

- `no OpenTofu/Terraform binary found`: install OpenTofu or Terraform ([Installation](installation.md)) or point `IACFORGE_TF_BINARY` at one. If you set `IACFORGE_TF_BINARY`, only that value is tried.
- `pulumi CLI not found` or `pulumi Python SDK not installed`: install the Pulumi CLI and `iacforge[pulumi]` (or the provider extra such as `iacforge[pulumi-docker]`).
- `iacforge-mcp` exits 3 when the `mcp` extra is missing: `uv tool install "iacforge[mcp] @ git+https://github.com/bsommers/iacforge"`.

### `engine_failed` (exit 4)

The engine ran and returned an error. `details.stderr` holds the last lines of its output and `details.command` the exact command. Common provider-level causes:

| Symptom (in `details`) | Fix |
|---|---|
| `Cannot connect to the Docker daemon` / socket permission denied | Start Docker; add your user to the `docker` group; or set `providerConfig.host` (Colima, Podman, Windows pipe). |
| `Pool overlaps with other one on this address space` | A docker `network.subnet` collides with an existing network (`docker network ls`). Omit `subnet` or change it. |
| `port is already allocated` | Another process or container uses the host port: change `ports[].external`. |
| `Failed to query available provider packages` / timeout during `init` | The engine could not reach the provider registry. Check network, proxy and `HTTPS_PROXY`. |
| libvirt: `failed to connect to the hypervisor` / permission denied | The libvirt daemon is down, or your user is not in the `libvirt` group: `virsh -c qemu:///system list` must work. |
| gcp: `could not find default credentials` | Run `gcloud auth application-default login` or set `GOOGLE_APPLICATION_CREDENTIALS`. |
| gcp: `API [compute.googleapis.com] not enabled` | Enable the API on the project: `gcloud services enable compute.googleapis.com storage.googleapis.com iam.googleapis.com`. |
| aws: `no valid credential sources` | Set `AWS_PROFILE`/env credentials or run `aws sso login`; check `providerConfig.profile` and `region`. |
| bucket name already taken | GCS and S3 bucket names are globally unique: set `bucketName`. |

To reproduce by hand, render and run the engine yourself:

```sh
iacforge render --workdir ./debug
cd debug && tofu init && tofu plan
```

### `not_confirmed` (exit 5)

`apply` and `destroy` need `--yes` (CLI), `confirm=True` (Python) or `confirm: true` (MCP). With `--json` or a non-interactive stdin there is no prompt. This is deliberate.

### `internal` (exit 1)

An unexpected exception: the message is `<ExceptionType>: <text>`. Please open an issue at <https://github.com/bsommers/iacforge/issues> with the spec (secrets removed) and the output of `iacforge --json version`.

## Other problems

**`iacforge: error: unrecognized arguments: --json`**
`--json` is a global option and goes before the command: `iacforge --json plan`. Alternatively export `IACFORGE_OUTPUT=json`.

**`iacforge: command not found` after install.**
Run `uv tool update-shell` (or `pipx ensurepath`) and restart the shell, or run it from the virtualenv: `.venv/bin/iacforge`.

**A warning says the provider does not run on this host platform.**
`validate` and `render` still work (useful for review in CI), but `apply` will probably fail: hyperv needs Windows, libvirt needs Linux.

**My file was not created where I expected (`local` provider).**
Relative paths resolve inside the workdir: `.iacforge/<stack>/<engine>/<path>`. Use an absolute path to write elsewhere.

**`plan` shows everything as new after I switched engines.**
State is per engine (`.iacforge/<stack>/<engine>/`). Destroy with the engine that created the resources, or keep using it.

**I deleted `.iacforge/` and now resources are orphaned.**
State lived there. Re-adopting resources (`import`) is on the [roadmap](../ROADMAP.md); until then remove the resources manually (for docker: `docker ps -a`, `docker network ls`).

**Pulumi: `passphrase` errors on a later run.**
You changed `PULUMI_CONFIG_PASSPHRASE` after the stack was created. Use the same value as at first apply (default is empty).

**Pulumi `plan` returns no per-resource list.**
Expected: under Pulumi `resources` is empty and only `changes` counts are reported.

**`terraform ok` in `doctor` although only `tofu` is installed.**
Expected: each engine falls back to the other binary ([Engines](engines.md)).

**Secrets show up in `main.tf.json` / state.**
Anything written in the spec is rendered verbatim. Use ambient credentials (ADC, AWS env, `HYPERV_PASSWORD`) and keep `.iacforge/` out of version control.
