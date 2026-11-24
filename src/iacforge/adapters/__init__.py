"""Provider registry. Register a provider by adding its module to ADAPTER_MODULES.

Each module must define exactly one ``ProviderAdapter`` subclass exported as ``ADAPTER``.
Modules are imported lazily so a broken/optional provider never breaks the others.
"""

from __future__ import annotations

import importlib

from ..errors import UnknownProviderError
from .base import ProviderAdapter

# provider name -> module (relative to this package)
ADAPTER_MODULES: dict[str, str] = {
    "local": ".local_file",
    "docker": ".docker",
    "libvirt": ".libvirt",
    "hyperv": ".hyperv",
    "multipass": ".multipass",
    "aws": ".aws",
    "gcp": ".gcp",
}

_cache: dict[str, ProviderAdapter] = {}


def provider_names() -> list[str]:
    return sorted(ADAPTER_MODULES)


def get_adapter(name: str) -> ProviderAdapter:
    if name in _cache:
        return _cache[name]
    mod_name = ADAPTER_MODULES.get(name)
    if mod_name is None:
        raise UnknownProviderError(
            f"unknown provider '{name}'", details={"known": provider_names()}
        )
    mod = importlib.import_module(mod_name, __name__)
    adapter = mod.ADAPTER
    if not isinstance(adapter, ProviderAdapter) or adapter.name != name:
        raise RuntimeError(f"module {mod_name} does not export ADAPTER for provider '{name}'")
    _cache[name] = adapter
    return adapter


def all_adapters() -> list[ProviderAdapter]:
    return [get_adapter(n) for n in provider_names()]
