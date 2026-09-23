"""Authorization and translation policy for provider-neutral query execution."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import EngineCapabilities, QueryRequest


def _identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty trimmed text")
    if any(char in value for char in "\r\n\x00"):
        raise ValueError(f"{name} must be single-line text")
    return value


@dataclass(frozen=True, slots=True)
class QueryExecutionPolicy:
    """Explicit profile/engine allowlists; no provider credentials are accepted."""

    profile_engines: tuple[tuple[str, tuple[str, ...]], ...]
    required_capability: str | None = None

    def __post_init__(self) -> None:
        profiles = tuple(sorted(self.profile_engines))
        if len({profile for profile, _ in profiles}) != len(profiles):
            raise ValueError("query profiles must be unique")
        for profile, engines in profiles:
            _identifier(profile, "query profile")
            if not engines or len(set(engines)) != len(engines):
                raise ValueError("query profile allowlists must be non-empty and unique")
            for engine in engines:
                _identifier(engine, "query engine")
        if self.required_capability is not None and not self.required_capability.strip():
            raise ValueError("required capability must be non-empty")
        if self.required_capability is not None:
            _identifier(self.required_capability, "required capability")
        object.__setattr__(self, "profile_engines", profiles)

    def allowed_engines(self, profile: str) -> tuple[str, ...]:
        for name, engines in self.profile_engines:
            if name == profile:
                return engines
        raise PermissionError("query profile is not authorized")

    def select_engine(
        self,
        request: QueryRequest,
        *,
        engine: str,
        capabilities: EngineCapabilities,
    ) -> str:
        if request.profile not in dict(self.profile_engines):
            raise PermissionError("query profile is not authorized")
        if engine not in self.allowed_engines(request.profile):
            raise PermissionError("query engine is not authorized for profile")
        if (
            self.required_capability is not None
            and capabilities.get(self.required_capability) is not True
        ):
            raise PermissionError("required query engine capability is unavailable")
        if (
            request.translation_policy == "strict"
            and capabilities.get("strict_translation") is not True
        ):
            raise PermissionError("strict translation is not qualified by the selected engine")
        if (
            request.translation_policy in {"best_effort", "strict"}
            and capabilities.get("translation") is not True
        ):
            raise PermissionError("translation is not qualified by the selected engine")
        return engine


__all__ = ("QueryExecutionPolicy",)
