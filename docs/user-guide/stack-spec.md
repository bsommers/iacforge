# Stack spec reference

A stack spec is a YAML (or JSON; YAML is a superset) document with one shape for every provider. Print its JSON Schema with `iacforge schema`; print one provider's `providerConfig` and per-resource-type schemas with `iacforge schema <provider>`. The CLI also reads a spec from stdin with `-`.

```yaml
apiVersion: iacforge/v1
kind: Stack
metadata:
  name: dev
  labels: {team: platform}
spec:
  provider: docker
  engine: opentofu
  providerConfig: {}
  resources:
    - name: net
      type: network
      properties: {}
    - name: web
      type: container
      properties:
        image: nginx:1.27-alpine
        ports: [{internal: 80, external: 8089}]
        networks: [net]
      dependsOn: []
```

Unknown keys are rejected everywhere (top level, `metadata`, `spec`, resources, and provider `properties`), so typos fail at `validate` instead of being silently ignored.

## Top-level fields

| Field | Type | Required | Description |
|---|---|---|---|
| `apiVersion` | string | yes | Must be exactly `iacforge/v1`. |
| `kind` | string | yes | Must be exactly `Stack`. |
| `metadata.name` | string | yes | Stack name. Also the key for the workdir and Pulumi stack. Pattern `^[a-z][a-z0-9-]{0,62}$`. |
| `metadata.labels` | map of string | no | Free-form labels. Not currently passed to providers. |
| `spec.provider` | string | yes | One of `aws`, `docker`, `gcp`, `hyperv`, `libvirt`, `local`, `multipass` (`iacforge providers`). |
| `spec.engine` | enum | no | `opentofu` (default), `terraform` or `pulumi`. Overridable per command with `--engine`. |
| `spec.providerConfig` | map | no | Provider-level settings, validated by the provider (for example `project` for gcp, `host` for docker). Defaults to `{}`. See each [provider page](providers/local.md). |
| `spec.resources` | list | no | The resources. An empty list is valid. |

A stack uses exactly one provider. Multi-provider stacks are on the [roadmap](../ROADMAP.md).

## Resources

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Unique within the stack. Pattern `^[a-z][a-z0-9-]{0,62}$`: lowercase letters, digits and hyphens, starting with a letter. |
| `type` | string | yes | Resource type offered by the provider (`container`, `vm`, `network`, `bucket`, `file`, ...). `iacforge providers <name>` lists them. |
| `properties` | map | no | Type-specific properties, validated by the provider. Defaults to `{}`. |
| `dependsOn` | list of string | no | Names of resources that must be created first. |

### Naming rules

- Spec resource names use lowercase, digits and `-`. In rendered Terraform, a name becomes an identifier by replacing every character outside `[A-Za-z0-9_]` with `_`, so `web-1` becomes `web_1`. Names that would start with a digit get an `r_` prefix (not reachable through the name pattern, but relevant for hand-edited output).
- The Terraform address of a resource is `<provider resource type>.<identifier>`, for example `docker_container.web_1`. Extra helper blocks an adapter emits are named `<identifier>_<suffix>` (for example `web_base`, `web_root`, `web_cloudinit` for a libvirt VM).
- Outputs are flattened to `<identifier>__<key>` inside the engine and re-nested for you. `apply` and `outputs` return `{"web-1": {"ip_address": "...", "name": "..."}}`, keyed by your original resource names.
- Pulumi logical resource names are the stack resource names.

### Dependencies

Order is computed deterministically (dependencies first, ties broken by declaration order).

- Explicit: `dependsOn: [net]`. Unknown names, duplicate resource names, self-dependency and cycles are validation errors (`dependency cycle: a -> b -> a`).
- Implicit: properties that name another resource are treated as dependencies automatically and the target must exist and have the right type. Examples: docker `container.networks`, `imageFrom`, `volumes[].volume`; libvirt `networkRef`, `poolRef`; hyperv `switchRef`, `vhdRef`; gcp `subnet.network`, `vm.subnet`, `vm.serviceAccount`; aws `subnet.vpc`, `vm.subnet`, `vm.securityGroups`. Each provider page lists them.

## Validation layers

`iacforge validate` runs, in order:

1. Generic shape (`invalid_spec`): fields above, name patterns, duplicates, `dependsOn`, cycles.
2. Provider lookup (`unknown_provider`) and engine support (`unsupported`, for example `engine: pulumi` with `hyperv`).
3. Provider `providerConfig` and every resource's `properties`, plus cross-resource checks. Errors are reported with a `path`, for example `spec.resources[0].properties.pth`.

Validation succeeds even on the wrong host OS but adds a warning (for example hyperv on Linux: `render works, apply will likely fail`).

Validation errors (exit code 2):

```
error[invalid_spec]: spec failed validation
  - metadata.name: String should match pattern '^[a-z][a-z0-9-]{0,62}$'
```

## Working directory and state

Everything iacforge writes for a stack goes under one directory:

```
<directory of the spec file>/.iacforge/<stack name>/<engine>/
```

Examples: `./.iacforge/dev/opentofu/`, `./.iacforge/dev/pulumi/`. When the spec comes from stdin or inline text, the base is the current directory. Override with `--workdir DIR` (CLI) or `workdir=` (Python/MCP).

| Engine | Files in the workdir |
|---|---|
| opentofu / terraform | `main.tf.json`, `.terraform/`, `.terraform.lock.hcl`, `tfplan`, `terraform.tfstate` (+ `.backup`) |
| pulumi | `Pulumi.yaml`, `__main__.py`, `requirements.txt`, `stack.json`, `state/` (file backend) |

Consequences:

- **State is local and per engine.** Switching `engine` for an applied stack starts from empty state in a different directory; destroy with the original engine first.
- **Relative paths** in resources (such as the `local` provider's `path`) resolve inside the workdir.
- Add `.iacforge/` to `.gitignore`: it contains state, which can include secrets.
- Run `destroy` before deleting a workdir, otherwise you lose track of what exists.
- Remote state: `spec.backend: {type: gcs, ...}` (gcp provider) keeps state in a GCS bucket instead; see [state backends](state-backends.md).

`apply` and `destroy` re-render the config each time, so editing `stack.yaml` and re-applying updates the stack.

## Secrets

Do not put credentials in a spec; specs are meant to be committed and shared. Use ADC (gcp), the AWS environment (aws), `HYPERV_USER`/`HYPERV_PASSWORD` (hyperv), or `docker login` for registries (docker `registryAuth` takes only `address` and `configFile`, never a password). Anything you do put in a spec (for example hyperv `password`) is rendered into `main.tf.json` and stored in state in plain text.

## Further reading

- [CLI reference](cli-reference.md), [Engines](engines.md)
- Machine-readable: `iacforge schema` and `iacforge schema <provider>`; the repo ships [`docs/agents/spec.schema.json`](../agents/spec.schema.json).
