# ADR 0005: Optional `spec.backend` selects where state lives

Status: accepted (2026-11-25)

## Context
v0.1 keeps all state in the workdir (`terraform.tfstate`, Pulumi `file://<workdir>/state`).
That is fine for one person on one machine, but state cannot be shared, locked or recovered.
v0.2 adds GCS remote state ([gcp-plan.md](../system/gcp-plan.md) section 2), and later S3 should fit
the same shape.

## Decision
`spec.backend` is an optional, provider-neutral section (`spec.Backend`, `extra="forbid"`):

```yaml
backend:
  type: gcs              # local (default) | gcs
  bucket: my-state-bkt   # required for gcs, forbidden for local
  prefix: iacforge       # optional, default "iacforge"
```

- Omitting it equals `{type: local}`; v0.1 specs are unchanged (additive change).
- Adapters declare `backends: ClassVar[frozenset[str]]` (default `{"local"}`; gcp: `{"local", "gcs"}`).
  `render.bind()` rejects an unsupported type with `UnsupportedError` (code `unsupported`).
- **State key** (one place, `Backend.state_key(stack, engine)`): `<prefix>/<stack name>/<engine>`.
  Engines never share a state object, so switching engine never corrupts state.
- **Terraform**: `render_terraform` emits `terraform.backend.gcs = {bucket, prefix: <state key>}`.
  `init` runs with `-reconfigure` whenever the rendered config changes; iacforge never migrates
  state implicitly.
- **Pulumi**: backend URL `gs://<bucket>/<state key>` (used for `PULUMI_BACKEND_URL` and the
  ejected `Pulumi.yaml`). With a remote backend, `PULUMI_CONFIG_PASSPHRASE` must be set and
  non-empty; otherwise the engine raises `SpecError` before touching state.
- No credentials in `backend`: access comes from ambient ADC, like the provider.
- The state bucket is never created by the stack that stores in it (bootstrap is documented).

## Consequences
Remote state is opt-in, per stack. The workdir still holds rendered files and the provider cache
but no state when `type: gcs`. Adding `s3` later is a new `Literal` value plus engine branches.
