"""Fail-closed provider/model qualification for the local GenAI profile."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from studio_core.genai import GenAIModel, ModelProvider


@dataclass(frozen=True, slots=True)
class ProviderQualification:
    provider_id: str
    model_id: str
    adapter: str
    capabilities: tuple[str, ...]
    status: str
    findings: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "adapter": self.adapter,
            "capabilities": list(self.capabilities),
            "status": self.status,
            "findings": list(self.findings),
        }


def qualify_provider_model(provider: ModelProvider, model: GenAIModel) -> ProviderQualification:
    """Return a deterministic qualification record; unknowns never pass."""

    findings: list[str] = []
    if model.provider_id != provider.id:
        findings.append("model_provider_mismatch")
    if provider.adapter not in {"openai-compatible", "openai_compatible"}:
        findings.append("adapter_not_qualified")
    if provider.endpoint is None:
        findings.append("provider_endpoint_missing")
    else:
        parsed = urlsplit(provider.endpoint)
        allow_http = dict(provider.properties).get("allow_http", "false").casefold() == "true"
        if parsed.scheme != "https" and not (allow_http and parsed.scheme == "http"):
            findings.append("provider_endpoint_not_secure")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            findings.append("provider_endpoint_contains_unsafe_components")
    return ProviderQualification(
        provider.id.value,
        model.model_id,
        provider.adapter,
        tuple(sorted(model.capabilities)),
        "qualified" if not findings else "rejected",
        tuple(findings),
    )


def qualify_model_payload(
    provider: ModelProvider, model_id: object, capabilities: object
) -> ProviderQualification:
    """Validate public model fields and apply deterministic qualification rules."""

    if not isinstance(model_id, str) or not model_id.strip() or "\x00" in model_id:
        raise ValueError("model_id must be a non-empty safe string")
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("capabilities must be a non-empty list")
    if not all(isinstance(value, str) and value.strip() for value in capabilities):
        raise ValueError("capabilities must contain non-empty strings")
    if len(set(capabilities)) != len(capabilities):
        raise ValueError("capabilities must be unique")
    return qualify_provider_model(
        provider,
        GenAIModel(provider.id, model_id, frozenset(capabilities)),
    )


__all__ = ("ProviderQualification", "qualify_model_payload", "qualify_provider_model")
