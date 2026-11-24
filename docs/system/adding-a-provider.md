# Adding a provider

A provider is one module under `src/iacforge/adapters/`, one line in the registry, tests, and a docs
page. This tutorial builds a minimal but complete adapter, `random` (the `hashicorp/random`
provider), end to end. Read [contracts.md](contracts.md) first for the full attribute list.

Rule of thumb ([ADR 0003](../adr/0003-plugin-contract.md)): adapters are pure translation. No
subprocesses, no filesystem, no state, no `if platform == ...`; capabilities go in class attributes.
Prefer the `local` adapter (`adapters/local_file.py`) as a reference and `adapters/gcp.py` as a
richer one with cross-resource references.

## 1. Decide the shape

- Provider name (`spec.provider`): lowercase, e.g. `random`.
- Resource types and their properties: curated, typed, documented. Use spec-style camelCase aliases
  (`byteLength`) with snake_case Python attributes.
- Engines: Terraform family only, or also Pulumi. Pulumi needs `pulumi_resource()` and the pip
  package in `pulumi_packages`.
- Host platforms and required host tools (`platforms`, `required_tools`).
- Status: new providers start as `scaffold` or `beta`.

## 2. Write the module

`src/iacforge/adapters/random_id.py` (the module name may differ from the provider name):

```python
"""`random` provider: random identifiers (hashicorp/random). Tutorial example."""

from __future__ import annotations

from pydantic import Field

from .base import ALL_PLATFORMS, TF, Props, ProviderAdapter, TfResult, tf_id


class IdProps(Props):
    byte_length: int = Field(default=8, ge=1, le=64, alias="byteLength")
    prefix: str = ""


class RandomAdapter(ProviderAdapter):
    name = "random"
    description = "Random identifiers (hashicorp/random). Terraform engines only."
    status = "beta"
    category = "local"
    platforms = ALL_PLATFORMS
    engines = frozenset({TF})
    resource_models = {"id": IdProps}
    tf_types = {"id": "random_id"}
    tf_required_providers = {"random": {"source": "hashicorp/random", "version": "~> 3.6"}}
    docs_url = "https://registry.terraform.io/providers/hashicorp/random/latest/docs"

    def tf_resource(self, res, props: IdProps, ctx) -> TfResult:
        addr = f"random_id.{tf_id(res.name)}"
        body = {"byte_length": props.byte_length}
        if props.prefix:
            body["prefix"] = props.prefix
        return TfResult(body, outputs={"hex": "${" + addr + ".hex}", "b64": "${" + addr + ".b64_url}"})


ADAPTER = RandomAdapter()

EXAMPLES = [{
    "apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "random-example"},
    "spec": {"provider": "random", "resources": [
        {"name": "suffix", "type": "id", "properties": {"byteLength": 4, "prefix": "app-"}}]},
}]
```

Points to notice:

- Models extend `Props` (`extra="forbid"`): a misspelled property is a validation error.
- `tf_types` maps every resource type to the Terraform resource type; `tf_required_providers`
  becomes `terraform.required_providers` (pin with `~>`).
- Outputs are returned under plain keys. `render_terraform` publishes them as
  `<tf_id(name)>__<key>` and engines nest them back to `{resource: {key: value}}`.
- The primary block is stored for you at `<tf_type>.<tf_id(name)>`; build interpolations either by
  hand from `tf_id` (as above) or with `ctx.ref(other_resource, "attr")` for *other* resources.
- Do not mutate `res`, `props` or `ctx`; do not use sets/time/random in output (determinism).

### References between resources

If a property names another stack resource (say `network: vpc`), implement:

```python
def references(self, res, props):
    return [props.network] if getattr(props, "network", None) else []
```

and render the real link with `ctx.ref(props.network, "self_link")`. Use `validate_stack()` to
return error strings when the referenced resource has the wrong type.

### Pulumi (optional)

Add `PULUMI` to `engines`, list `pulumi_packages = ("pulumi", "pulumi-<provider>")`, and implement
`pulumi_resource()` returning `PulumiResult(resource, outputs)`. Import the SDK inside the method,
wire options with `render.pulumi_opts(ctx, res)`, and fetch dependencies with `ctx.get(name)`.
Optionally return an explicit provider from `pulumi_provider()`. Add the matching extra in
`pyproject.toml` (`pulumi-<provider> = [...]`).

## 3. Register it

In `src/iacforge/adapters/__init__.py`:

```python
ADAPTER_MODULES: dict[str, str] = {
    ...
    "random": ".random_id",
}
```

The module is imported lazily; it must export `ADAPTER` (an instance whose `name` equals the key).
Also add any new host tool to `HOST_TOOLS` in `core.py` if `doctor` should report it
(optional; `doctor` falls back to `shutil.which`).

## 4. Tests

The shared contract suite (`tests/test_adapter_contract.py`) picks up the new provider
automatically via `provider_names()`; it needs `EXAMPLES` covering every resource type. Check it:

```bash
uv run pytest -q tests/test_adapter_contract.py -k random
```

(the `tofu`-marked test also runs real `tofu init` + `validate`, which needs network access to
fetch the provider; deselect with `-m "not tofu"` offline).

Then add `tests/test_adapter_random.py` modelled on `tests/test_adapter_gcp.py`:

```python
import copy

import pytest

from iacforge.adapters.random_id import EXAMPLES
from iacforge.errors import SpecError
from iacforge.render import bind, render_terraform
from iacforge.spec import parse_spec


def test_structure():
    out = render_terraform(bind(parse_spec(copy.deepcopy(EXAMPLES[0])), "opentofu"))
    assert out["resource"]["random_id"]["suffix"] == {"byte_length": 4, "prefix": "app-"}
    assert out["output"]["suffix__hex"]["value"] == "${random_id.suffix.hex}"


def test_rejects_bad_length():
    doc = copy.deepcopy(EXAMPLES[0])
    doc["spec"]["resources"][0]["properties"]["byteLength"] = 0
    with pytest.raises(SpecError):
        bind(parse_spec(doc))
```

Cover: structure of every resource type, outputs, defaults, each validator (negative cases),
references and wrong-type references, deterministic key order, and (if `pulumi_resource` exists) a
mocked Pulumi program (see `test_pulumi_program_with_mocks` in `tests/test_adapter_docker.py`).
Live tests need the right markers (`tofu`, `docker`, ...) and must destroy what they create.

## 5. Docs and checks

- Add a provider page under `docs/` (resource types, properties table, outputs, prerequisites,
  a worked example stack) and list the provider in the README and `docs/ROADMAP.md`.
- Run the gates:

```bash
uv run ruff check .
uv run pytest -q
iacforge providers random        # confirm it shows up
iacforge schema random           # confirm the JSON Schema
```

- If you changed a contract (new base-class attribute, new engine behaviour) write an ADR in
  `docs/adr/`.

## Checklist

- [ ] module exports `ADAPTER` and `EXAMPLES` covering every type
- [ ] registered in `ADAPTER_MODULES`
- [ ] every `resource_models` key present in `tf_types`; `tf_required_providers` pinned
- [ ] no credentials in `config_model`; secrets are references only
- [ ] `references()` / `validate_stack()` for cross-resource properties
- [ ] deterministic output; no mutation of inputs
- [ ] tests (contract + provider specific), docs page, `ruff` clean
