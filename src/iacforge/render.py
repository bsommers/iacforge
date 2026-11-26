"""Engine-independent rendering: validated stack -> Terraform JSON document / Pulumi resources.

Pure functions, no I/O. Output is deterministic (sorted keys when serialised, topo order).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from .adapters import get_adapter
from .adapters.base import (
    PULUMI,
    TF,
    Props,
    ProviderAdapter,
    PulumiContext,
    TfContext,
    output_key,
    tf_id,
)
from .errors import SpecError, UnsupportedError
from .spec import Resource, StackSpec, topo_order

ENGINE_FAMILY = {"opentofu": TF, "terraform": TF, "pulumi": PULUMI}


@dataclass
class BoundStack:
    """A stack whose provider config and resource properties passed adapter validation."""

    stack: StackSpec
    adapter: ProviderAdapter
    config: Props
    props: dict[str, Props]
    order: list[Resource]
    warnings: list[str] = field(default_factory=list)

    @property
    def engine(self) -> str:
        return self.stack.spec.engine

    @property
    def backend(self):  # spec.Backend
        return self.stack.spec.backend

    @property
    def state_key(self) -> str:
        return self.backend.state_key(self.stack.name, self.engine)


def _errs(e: ValidationError, prefix: str) -> list[dict]:
    return [
        {"path": prefix + "".join(f".{p}" for p in err.get("loc", ())), "message": err.get("msg", "")}
        for err in e.errors()
    ]


def bind(stack: StackSpec, engine: str | None = None) -> BoundStack:
    """Validate a parsed stack against its provider adapter. Raises SpecError/UnsupportedError."""
    adapter = get_adapter(stack.spec.provider)
    eng = engine or stack.spec.engine
    if eng not in ENGINE_FAMILY:
        raise SpecError(f"unknown engine '{eng}'", details={"known": sorted(ENGINE_FAMILY)})
    if ENGINE_FAMILY[eng] not in adapter.engines:
        raise UnsupportedError(
            f"provider '{adapter.name}' does not support engine '{eng}'",
            details={"supported": adapter.describe()["engines"]},
        )
    if stack.spec.backend.type not in adapter.backends:
        raise UnsupportedError(
            f"provider '{adapter.name}' does not support backend '{stack.spec.backend.type}'",
            details={"supported": sorted(adapter.backends)},
        )
    if eng != stack.spec.engine:
        stack = stack.model_copy(update={"spec": stack.spec.model_copy(update={"engine": eng})})

    errors: list[dict] = []
    config: Props | None = None
    try:
        config = adapter.config_model.model_validate(stack.spec.provider_config)
    except ValidationError as e:
        errors += _errs(e, "spec.providerConfig")

    props: dict[str, Props] = {}
    for i, r in enumerate(stack.spec.resources):
        model = adapter.resource_models.get(r.type)
        if model is None:
            errors.append({
                "path": f"spec.resources[{i}].type",
                "message": f"provider '{adapter.name}' has no resource type '{r.type}' "
                f"(supported: {', '.join(sorted(adapter.resource_models))})",
            })
            continue
        try:
            props[r.name] = model.model_validate(r.properties)
        except ValidationError as e:
            errors += _errs(e, f"spec.resources[{i}].properties")
    if errors:
        raise SpecError("spec failed provider validation", details=errors)
    assert config is not None

    # implicit references become dependencies
    names = {r.name for r in stack.spec.resources}
    resources = []
    for r in stack.spec.resources:
        refs = adapter.references(r, props[r.name])
        missing = [x for x in refs if x not in names]
        if missing:
            errors.append({"path": f"resources.{r.name}", "message": f"references unknown resource(s): {', '.join(missing)}"})
        deps = list(dict.fromkeys([*r.depends_on, *[x for x in refs if x in names and x != r.name]]))
        resources.append(r.model_copy(update={"depends_on": deps}))
    for msg in adapter.validate_stack(stack, config, props):
        errors.append({"path": "spec", "message": msg})
    if errors:
        raise SpecError("spec failed provider validation", details=errors)
    try:
        order = topo_order(resources)
    except ValueError as e:
        raise SpecError(str(e)) from None
    return BoundStack(stack=stack, adapter=adapter, config=config, props=props, order=order)


def render_terraform(b: BoundStack) -> dict[str, Any]:
    """Return the full Terraform JSON configuration document (main.tf.json)."""
    a = b.adapter
    ctx = TfContext(stack=b.stack, config=b.config, adapter=a)
    doc: dict[str, Any] = {"terraform": {"required_providers": dict(a.tf_required_providers)}}
    providers = a.tf_provider_blocks(b.config)
    if providers:
        doc["provider"] = providers
    resources: dict[str, dict[str, Any]] = {}
    data: dict[str, dict[str, Any]] = {}
    outputs: dict[str, Any] = {}
    for r in b.order:
        result = a.tf_resource(r, b.props[r.name], ctx)
        body = dict(result.body)
        if r.depends_on:
            body["depends_on"] = sorted(ctx.address(d) for d in r.depends_on)
        tf_type = a.tf_types[r.type]
        resources.setdefault(tf_type, {})[tf_id(r.name)] = body
        for t, blocks in result.extra.items():
            resources.setdefault(t, {}).update(blocks)
        for t, blocks in result.data.items():
            data.setdefault(t, {}).update(blocks)
        for k, expr in result.outputs.items():
            outputs[output_key(r.name, k)] = {"value": expr}
    if data:
        doc["data"] = data
    if resources:
        doc["resource"] = resources
    if outputs:
        doc["output"] = outputs
    return doc


def terraform_json(b: BoundStack) -> str:
    return json.dumps(render_terraform(b), indent=2, sort_keys=True) + "\n"


def run_pulumi_program(b: BoundStack) -> None:
    """Body of the Pulumi program: create every resource in dependency order and export outputs.

    Must be called inside a Pulumi program context (Automation API inline program or
    an ejected project's __main__.py)."""
    import pulumi  # optional dependency, imported only under the pulumi engine

    a = b.adapter
    ctx = PulumiContext(stack=b.stack, config=b.config, provider=a.pulumi_provider(b.config, b.stack))
    for r in b.order:
        result = a.pulumi_resource(r, b.props[r.name], ctx)
        ctx.resources[r.name] = result.resource
        for k, v in result.outputs.items():
            pulumi.export(output_key(r.name, k), v)


def pulumi_opts(ctx: PulumiContext, res: Resource, **extra: Any):
    """ResourceOptions with explicit provider + dependsOn wired. Adapters should use this."""
    import pulumi

    deps = [ctx.resources[d] for d in res.depends_on if d in ctx.resources]
    kw: dict[str, Any] = {"depends_on": deps} if deps else {}
    if ctx.provider is not None:
        kw["provider"] = ctx.provider
    kw.update(extra)
    return pulumi.ResourceOptions(**kw)


def nest_outputs(flat: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{"web__ip": 1} -> {"web": {"ip": 1}} (resource key is the tf_id form)."""
    out: dict[str, dict[str, Any]] = {}
    for k, v in sorted(flat.items()):
        res, sep, key = k.partition("__")
        if not sep:
            res, key = "_", k
        out.setdefault(res, {})[key] = v
    return out
