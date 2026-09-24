"""Provider-neutral query-engine contracts for optional external engines."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from studio_core.canonical_json import encode as encode_canonical_json

QueryState = Literal["queued", "running", "succeeded", "failed", "cancelled"]
TranslationPolicy = Literal["native_only", "best_effort", "strict"]

# Stable Ronin-owned boundary for optional external query providers.  Providers
# may add fields in their own payloads, but must not replace this identity.
QUERY_ENGINE_NAMESPACE = "ronin.query-engine"
QUERY_ENGINE_VERSION = "v1"


def _text(value: str, name: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty trimmed text")
    if any(char in value for char in "\r\n\x00"):
        raise ValueError(f"{name} must be single-line text")
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds its maximum length")
    return value


def _json(value: object) -> str:
    return encode_canonical_json(value).decode("utf-8")


def _digest(value: str, name: str) -> str:
    _text(value, name, maximum=64)
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    return value


@dataclass(frozen=True, slots=True)
class EngineCapabilities:
    """Capability values are true, false, or unknown (None)."""

    values: tuple[tuple[str, bool | None], ...]

    def __post_init__(self) -> None:
        normalized = tuple(
            sorted((_text(key, "capability name"), value) for key, value in self.values)
        )
        if any(not isinstance(value, (bool, type(None))) for _, value in normalized):
            raise ValueError("capability values must be boolean or unknown")
        if len({key for key, _ in normalized}) != len(normalized):
            raise ValueError("capability names must be unique")
        object.__setattr__(self, "values", normalized)

    def get(self, name: str) -> bool | None:
        return dict(self.values).get(name)

    def to_payload(self) -> dict[str, object]:
        return {"values": dict(self.values)}


@dataclass(frozen=True, slots=True)
class EngineHandshake:
    provider_id: str
    provider_version: str
    capabilities: EngineCapabilities
    healthy: bool
    cluster_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.provider_id, "provider_id")
        _text(self.provider_version, "provider_version")
        if not isinstance(self.healthy, bool):
            raise ValueError("healthy must be boolean")
        if self.cluster_id is not None:
            _text(self.cluster_id, "cluster_id")

    def to_payload(self) -> dict[str, object]:
        return {
            "contract": f"{QUERY_ENGINE_NAMESPACE}/{QUERY_ENGINE_VERSION}",
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "capabilities": self.capabilities.to_payload(),
            "healthy": self.healthy,
            "cluster_id": self.cluster_id,
        }


@dataclass(frozen=True, slots=True)
class QueryRequest:
    sql: str
    profile: str
    translation_policy: TranslationPolicy = "native_only"
    max_rows: int = 1_000

    def __post_init__(self) -> None:
        _text(self.sql, "sql", maximum=1_000_000)
        _text(self.profile, "profile")
        if self.translation_policy not in {"native_only", "best_effort", "strict"}:
            raise ValueError("unsupported translation policy")
        if isinstance(self.max_rows, bool) or not isinstance(self.max_rows, int):
            raise ValueError("max_rows must be an integer")
        if not 1 <= self.max_rows <= 1_000_000:
            raise ValueError("max_rows is outside the configured bound")

    def to_payload(self) -> dict[str, object]:
        return {
            "sql": self.sql,
            "profile": self.profile,
            "translation_policy": self.translation_policy,
            "max_rows": self.max_rows,
        }

    def canonical_json(self) -> str:
        return _json(self.to_payload())


@dataclass(frozen=True, slots=True)
class QueryHandle:
    query_id: str
    provider_id: str
    provider_query_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.query_id, "query_id")
        _text(self.provider_id, "provider_id")
        if self.provider_query_id is not None:
            _text(self.provider_query_id, "provider_query_id")


@dataclass(frozen=True, slots=True)
class QueryStatus:
    state: QueryState
    message: str | None = None
    provider_query_id: str | None = None

    def __post_init__(self) -> None:
        if self.state not in {"queued", "running", "succeeded", "failed", "cancelled"}:
            raise ValueError("unsupported query state")
        if self.message is not None:
            _text(self.message, "query status message", maximum=4_000)
        if self.provider_query_id is not None:
            _text(self.provider_query_id, "provider_query_id")


@dataclass(frozen=True, slots=True)
class QueryResultPage:
    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    next_page_token: str | None = None

    def __post_init__(self) -> None:
        columns = tuple(_text(value, "result column") for value in self.columns)
        if len(columns) != len(set(columns)):
            raise ValueError("result columns must be unique")
        rows = tuple(tuple(row) for row in self.rows)
        if any(len(row) != len(columns) for row in rows):
            raise ValueError("result row width must match columns")
        if self.next_page_token is not None:
            _text(self.next_page_token, "next_page_token")
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "rows", rows)


@dataclass(frozen=True, slots=True)
class CancellationResult:
    cancelled: bool
    final_state: QueryState

    def __post_init__(self) -> None:
        if not isinstance(self.cancelled, bool):
            raise ValueError("cancelled must be boolean")
        if self.final_state not in {"queued", "running", "succeeded", "failed", "cancelled"}:
            raise ValueError("unsupported cancellation final state")


@dataclass(frozen=True, slots=True)
class QueryEvidence:
    request_digest: str
    provider_id: str
    provider_query_id: str | None
    selected_engine: str | None
    timings_ms: tuple[tuple[str, int], ...] = ()
    translated_sql_digest: str | None = None
    cancelled: bool = False
    engine_stats: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        _digest(self.request_digest, "request_digest")
        _text(self.provider_id, "provider_id")
        if self.provider_query_id is not None:
            _text(self.provider_query_id, "provider_query_id")
        if self.selected_engine is not None:
            _text(self.selected_engine, "selected_engine")
        if self.translated_sql_digest is not None:
            _digest(self.translated_sql_digest, "translated_sql_digest")
        timings = tuple(sorted(self.timings_ms))
        if len({key for key, _ in timings}) != len(timings) or any(
            not _text(key, "timing name")
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for key, value in timings
        ):
            raise ValueError("timings must contain unique non-negative integer values")
        object.__setattr__(self, "timings_ms", timings)
        if not isinstance(self.cancelled, bool):
            raise ValueError("cancelled must be boolean")
        stats = tuple(sorted(self.engine_stats))
        if len({key for key, _ in stats}) != len(stats) or any(
            not _text(key, "engine stat name")
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for key, value in stats
        ):
            raise ValueError("engine_stats must contain unique non-negative integer values")
        object.__setattr__(self, "engine_stats", stats)

    def to_payload(self) -> dict[str, object]:
        return {
            "request_digest": self.request_digest,
            "provider_id": self.provider_id,
            "provider_query_id": self.provider_query_id,
            "selected_engine": self.selected_engine,
            "timings_ms": dict(self.timings_ms),
            "translated_sql_digest": self.translated_sql_digest,
            "cancelled": self.cancelled,
            "engine_stats": dict(self.engine_stats),
        }


__all__ = [
    "CancellationResult",
    "EngineCapabilities",
    "EngineHandshake",
    "QueryEvidence",
    "QueryHandle",
    "QueryRequest",
    "QueryResultPage",
    "QueryState",
    "QueryStatus",
    "TranslationPolicy",
    "QUERY_ENGINE_NAMESPACE",
    "QUERY_ENGINE_VERSION",
]
