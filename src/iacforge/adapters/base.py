"""Provider adapter contract.

A provider adapter teaches iacforge one infrastructure target (docker, libvirt, gcp, ...).
It is pure translation: validated spec in, engine-native description out. Adapters never
run processes or touch state; engines do that.

To add a provider: subclass ``ProviderAdapter`` in ``adapters/<name>.py``, fill in the class
attributes, implement ``tf_resource`` (and ``pulumi_resource`` if ``"pulumi"`` is in
``engines``), then add the module name to ``ADAPTER_MODULES`` in ``adapters/__init__.py``.
The shared contract tests in ``tests/test_adapter_contract.py`` run against every adapter.

Naming rules (deterministic, relied on by the engines):
* Terraform primary address of a stack resource is ``<tf_types[type]>.<tf_id(name)>``.
  Extra helper blocks an adapter emits must be named ``<tf_id(name)>_<suffix>``.
* Outputs are flattened as ``<tf_id(resource)>__<key>`` (double underscore) and
  re-nested by the engine into ``{resource: {key: value}}``.
* Pulumi logical resource name is the stack resource name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:  # pragma: no cover
    from ..spec import Resource, StackSpec

LINUX = "linux"
MACOS = "darwin"
WINDOWS = "windows"
ALL_PLATFORMS = frozenset({LINUX, MACOS, WINDOWS})

TF = "terraform"  # covers both opentofu and terraform binaries
PULUMI = "pulumi"

OUTPUT_SEP = "__"


class Props(BaseModel):
    """Base for adapter property/config models: unknown keys are errors (catches typos)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class EmptyConfig(Props):
    pass


def tf_id(name: str) -> str:
    """Stack resource name -> Terraform identifier ("web-1" -> "web_1")."""
    ident = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not re.match(r"^[A-Za-z_]", ident):
        ident = "r_" + ident
    return ident


def output_key(resource_name: str, key: str) -> str:
    return f"{tf_id(resource_name)}{OUTPUT_SEP}{key}"


@dataclass
class TfResult:
    """What an adapter returns for one stack resource under the Terraform engine.

    ``body``     – attributes of the primary ``resource "<tf_type>" "<tf_id>"`` block.
    ``extra``    – additional resource blocks: {tf_type: {block_name: body}}.
    ``data``     – data source blocks: {data_type: {block_name: body}}.
    ``outputs``  – {key: terraform expression string, e.g. "${docker_container.web.id}"}.
    """

    body: dict[str, Any]
    extra: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    data: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class TfContext:
    stack: "StackSpec"
    config: BaseModel
    adapter: "ProviderAdapter"

    def address(self, resource_name: str) -> str:
        """Primary Terraform address of another stack resource, e.g. 'docker_network.net'."""
        res = self.stack.resource(resource_name)
        return f"{self.adapter.tf_types[res.type]}.{tf_id(res.name)}"

    def ref(self, resource_name: str, attr: str) -> str:
        """Interpolation string for an attribute of another stack resource."""
        return "${" + f"{self.address(resource_name)}.{attr}" + "}"


@dataclass
class PulumiResult:
    resource: Any  # pulumi.Resource
    outputs: dict[str, Any] = field(default_factory=dict)  # key -> pulumi.Output / value


@dataclass
class PulumiContext:
    stack: "StackSpec"
    config: BaseModel
    provider: Any = None  # pulumi.ProviderResource or None
    resources: dict[str, Any] = field(default_factory=dict)  # stack name -> pulumi.Resource

    def get(self, resource_name: str) -> Any:
        """Already-created pulumi resource for a stack resource (dependencies are created first)."""
        return self.resources[resource_name]


class ProviderAdapter:
    # ---- identity & capabilities (class attributes; read by `iacforge providers`) ----
    name: ClassVar[str]
    description: ClassVar[str]
    status: ClassVar[str] = "stable"  # stable | beta | scaffold
    category: ClassVar[str] = "local"  # local | cloud
    platforms: ClassVar[frozenset[str]] = ALL_PLATFORMS  # host OSes it can provision from/on
    engines: ClassVar[frozenset[str]] = frozenset({TF, PULUMI})
    required_tools: ClassVar[tuple[str, ...]] = ()  # host binaries needed at apply time
    pulumi_packages: ClassVar[tuple[str, ...]] = ()  # pip packages needed by the pulumi engine
    config_model: ClassVar[type[Props]] = EmptyConfig
    resource_models: ClassVar[dict[str, type[Props]]] = {}
    tf_types: ClassVar[dict[str, str]] = {}  # resource type -> terraform resource type
    tf_required_providers: ClassVar[dict[str, dict[str, str]]] = {}
    docs_url: ClassVar[str] = ""

    # ---- validation ----
    def references(self, res: "Resource", props: Props) -> list[str]:
        """Stack resource names this resource refers to inside its properties.

        Treated as implicit dependsOn entries (ordering + existence checks)."""
        return []

    def validate_stack(self, stack: "StackSpec", config: Props, props: dict[str, Props]) -> list[str]:
        """Cross-resource checks beyond the pydantic models. Return error strings."""
        return []

    # ---- terraform engine ----
    def tf_provider_blocks(self, config: Props) -> dict[str, Any]:
        """`provider` block(s), e.g. {"docker": {"host": "unix:///var/run/docker.sock"}}."""
        return {}

    def tf_resource(self, res: "Resource", props: Props, ctx: TfContext) -> TfResult:
        raise NotImplementedError(f"{self.name}: terraform rendering not implemented")

    # ---- pulumi engine ----
    def pulumi_provider(self, config: Props, stack: "StackSpec") -> Any:
        """Explicit pulumi provider instance, or None to use ambient configuration."""
        return None

    def pulumi_resource(self, res: "Resource", props: Props, ctx: PulumiContext) -> PulumiResult:
        raise NotImplementedError(f"{self.name}: pulumi program not implemented")

    # ---- introspection helpers ----
    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "name": cls.name,
            "description": cls.description,
            "status": cls.status,
            "category": cls.category,
            "platforms": sorted(cls.platforms),
            "engines": sorted({"opentofu", "terraform"} if TF in cls.engines else set())
            + (["pulumi"] if PULUMI in cls.engines else []),
            "resource_types": sorted(cls.resource_models),
            "required_tools": list(cls.required_tools),
            "pulumi_packages": list(cls.pulumi_packages),
            "docs_url": cls.docs_url,
        }

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        return {
            "provider": cls.name,
            "providerConfig": cls.config_model.model_json_schema(by_alias=True),
            "resources": {
                t: m.model_json_schema(by_alias=True) for t, m in sorted(cls.resource_models.items())
            },
        }
