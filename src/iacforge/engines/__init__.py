"""Engine registry: opentofu/terraform share TerraformEngine (binary differs), pulumi has its own."""

from __future__ import annotations

from ..errors import SpecError
from .base import Engine, Runner

ENGINE_NAMES = ("opentofu", "terraform", "pulumi")


def get_engine(name: str, runner: Runner | None = None, which=None) -> Engine:
    if name in ("opentofu", "terraform"):
        from .terraform import TerraformEngine

        return TerraformEngine(flavor=name, runner=runner, which=which)
    if name == "pulumi":
        from .pulumi import PulumiEngine

        return PulumiEngine(runner=runner, which=which)
    raise SpecError(f"unknown engine '{name}'", details={"known": list(ENGINE_NAMES)})
