"""Typed errors. Every error carries a stable machine-readable code and a process exit code.

Agents should branch on ``code`` (stable), never on ``message`` (human text, may change).
"""

from __future__ import annotations

EXIT_OK = 0
EXIT_ERROR = 1          # unexpected/internal failure
EXIT_INVALID = 2        # bad CLI usage or invalid spec
EXIT_TOOL_MISSING = 3   # tofu/terraform/pulumi/docker/... not installed
EXIT_ENGINE = 4         # engine (tofu/pulumi) ran and failed
EXIT_NOT_CONFIRMED = 5  # mutating command without --yes / confirm=true


class IacForgeError(Exception):
    code = "error"
    exit_code = EXIT_ERROR

    def __init__(self, message: str, *, details: object | None = None):
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        d: dict = {"code": self.code, "message": self.message}
        if self.details is not None:
            d["details"] = self.details
        return d


class SpecError(IacForgeError):
    code = "invalid_spec"
    exit_code = EXIT_INVALID


class UnknownProviderError(SpecError):
    code = "unknown_provider"


class UnsupportedError(SpecError):
    """Provider does not support the requested resource type, engine or host platform."""

    code = "unsupported"


class ToolMissingError(IacForgeError):
    code = "tool_missing"
    exit_code = EXIT_TOOL_MISSING


class EngineError(IacForgeError):
    code = "engine_failed"
    exit_code = EXIT_ENGINE


class NotConfirmedError(IacForgeError):
    code = "not_confirmed"
    exit_code = EXIT_NOT_CONFIRMED
