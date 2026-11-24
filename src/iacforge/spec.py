"""Stack spec: the single provider-neutral input format (YAML or JSON).

Example::

    apiVersion: iacforge/v1
    kind: Stack
    metadata:
      name: dev
    spec:
      provider: docker          # see `iacforge providers`
      engine: opentofu          # opentofu | terraform | pulumi
      providerConfig: {}        # provider-specific, validated by the adapter
      resources:
        - name: web
          type: container
          properties: {image: "nginx:1.27", ports: [{internal: 80, external: 8080}]}
          dependsOn: []

Generic shape is validated here; per-provider ``properties`` are validated by the
provider adapter's pydantic models (see ``adapters/base.py``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .errors import SpecError

API_VERSION = "iacforge/v1"
NAME_PATTERN = r"^[a-z][a-z0-9-]{0,62}$"
ENGINES = ("opentofu", "terraform", "pulumi")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Metadata(_Model):
    name: str = Field(pattern=NAME_PATTERN, description="Stack name; also the state/workdir key.")
    labels: dict[str, str] = Field(default_factory=dict)


class Resource(_Model):
    name: str = Field(pattern=NAME_PATTERN, description="Unique within the stack.")
    type: str = Field(description="Resource type, e.g. container, vm, network, bucket, file.")
    properties: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, alias="dependsOn")


class StackBody(_Model):
    provider: str
    engine: Literal["opentofu", "terraform", "pulumi"] = "opentofu"
    provider_config: dict[str, Any] = Field(default_factory=dict, alias="providerConfig")
    resources: list[Resource] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_refs(self) -> "StackBody":
        names = [r.name for r in self.resources]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"duplicate resource names: {', '.join(dupes)}")
        known = set(names)
        for r in self.resources:
            for dep in r.depends_on:
                if dep not in known:
                    raise ValueError(f"resource '{r.name}' dependsOn unknown resource '{dep}'")
                if dep == r.name:
                    raise ValueError(f"resource '{r.name}' depends on itself")
        topo_order(self.resources)  # raises on cycles
        return self


class StackSpec(_Model):
    api_version: Literal["iacforge/v1"] = Field(alias="apiVersion")
    kind: Literal["Stack"]
    metadata: Metadata
    spec: StackBody

    @property
    def name(self) -> str:
        return self.metadata.name

    def resource(self, name: str) -> Resource:
        for r in self.spec.resources:
            if r.name == name:
                return r
        raise KeyError(name)


def topo_order(resources: list[Resource]) -> list[Resource]:
    """Deterministic topological order: dependencies first, ties broken by declaration order."""
    by_name = {r.name: r for r in resources}
    index = {r.name: i for i, r in enumerate(resources)}
    done: list[Resource] = []
    state: dict[str, int] = {}  # 1 = visiting, 2 = done

    def visit(name: str, path: list[str]) -> None:
        s = state.get(name)
        if s == 2:
            return
        if s == 1:
            raise ValueError("dependency cycle: " + " -> ".join(path + [name]))
        state[name] = 1
        for dep in sorted(by_name[name].depends_on, key=lambda d: index.get(d, 0)):
            if dep in by_name:
                visit(dep, path + [name])
        state[name] = 2
        done.append(by_name[name])

    for r in resources:
        visit(r.name, [])
    return done


def _format_validation(e: ValidationError) -> list[dict]:
    out = []
    for err in e.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        out.append({"path": loc, "message": err.get("msg", "")})
    return out


def parse_spec(data: Any) -> StackSpec:
    """Parse an already-loaded mapping into a StackSpec, raising SpecError with structured details."""
    if not isinstance(data, dict):
        raise SpecError("spec must be a mapping/object at the top level")
    try:
        return StackSpec.model_validate(data)
    except ValidationError as e:
        raise SpecError("spec failed validation", details=_format_validation(e)) from None


def load_spec_text(text: str) -> StackSpec:
    try:
        data = yaml.safe_load(text)  # YAML is a superset of JSON
    except yaml.YAMLError as e:
        raise SpecError(f"could not parse spec: {e}") from None
    return parse_spec(data)


def load_spec(path: str | Path) -> StackSpec:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise SpecError(f"cannot read spec file {p}: {e.strerror}") from None
    return load_spec_text(text)


def spec_json_schema() -> dict:
    """JSON Schema for the generic stack shape (per-provider schemas: `iacforge schema <provider>`)."""
    return StackSpec.model_json_schema(by_alias=True)


def dump_spec(spec: StackSpec) -> str:
    return json.dumps(spec.model_dump(by_alias=True, exclude_defaults=False), indent=2, sort_keys=True)
