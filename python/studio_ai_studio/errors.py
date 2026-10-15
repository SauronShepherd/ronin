"""Stable public error taxonomy for AI Studio."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AIStudioError(Exception):
    code: str
    message: str
    status: int = 500
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class InvalidRequest(AIStudioError):
    def __init__(self, message: str) -> None:
        super().__init__("invalid_request", message, 400, False)


class ModelNotFound(AIStudioError):
    def __init__(self, model: str) -> None:
        super().__init__("model_not_found", f"model is not configured: {model}", 404, False)


class CapabilityNotSupported(AIStudioError):
    def __init__(self, capability: str) -> None:
        super().__init__(
            "capability_not_supported", f"unsupported capability: {capability}", 400, False
        )


class EndpointUnavailable(AIStudioError):
    def __init__(self, endpoint: str) -> None:
        super().__init__("endpoint_unavailable", f"endpoint is unavailable: {endpoint}", 503, True)


class EndpointSaturated(AIStudioError):
    def __init__(self, endpoint: str) -> None:
        super().__init__("endpoint_saturated", f"endpoint is saturated: {endpoint}", 429, True)
