"""Versioned, deterministic classification metadata for governed assets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json

_LEVELS = {"public", "internal", "confidential", "restricted"}


def _labels(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    result = tuple(sorted(value.strip().casefold() for value in values))
    if any(not value or value != value.strip() for value in result):
        raise ValueError(f"{field} must contain non-empty labels")
    if len(result) != len(set(result)):
        raise ValueError(f"{field} must be unique")
    if "level" in field and any(value not in _LEVELS for value in result):
        raise ValueError("unsupported sensitivity level")
    return result


@dataclass(frozen=True, slots=True)
class SensitivityMetadata:
    """Immutable metadata revision with explicit and inherited labels.

    ``explicit`` is authored on the asset. ``inherited`` is supplied by the
    catalog resolver from parents; the effective set is their canonical union.
    Keeping both sets makes provenance visible and prevents accidental loss of
    an inherited restriction during an update.
    """

    version: int
    explicit: tuple[str, ...] = ()
    inherited: tuple[str, ...] = ()
    inherited_from: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("sensitivity metadata version must be positive")
        object.__setattr__(self, "explicit", _labels(self.explicit, "explicit labels"))
        object.__setattr__(self, "inherited", _labels(self.inherited, "inherited labels"))
        sources = tuple(sorted(source.strip() for source in self.inherited_from))
        if any(not source for source in sources) or len(sources) != len(set(sources)):
            raise ValueError("inherited_from must contain unique non-empty references")
        object.__setattr__(self, "inherited_from", sources)

    @property
    def effective(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.explicit) | set(self.inherited)))

    @property
    def effective_level(self) -> str | None:
        levels = [label for label in self.effective if label in _LEVELS]
        order = ("public", "internal", "confidential", "restricted")
        return max(levels, key=order.index) if levels else None

    def to_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "explicit": list(self.explicit),
            "inherited": list(self.inherited),
            "inherited_from": list(self.inherited_from),
            "effective": list(self.effective),
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> SensitivityMetadata:
        if not isinstance(payload, Mapping) or set(payload) != {
            "version",
            "explicit",
            "inherited",
            "inherited_from",
            "effective",
        }:
            raise ValueError("sensitivity metadata has invalid shape")
        version = payload["version"]
        if not isinstance(version, int) or isinstance(version, bool):
            raise ValueError("sensitivity metadata version must be an integer")
        fields = {name: payload[name] for name in ("explicit", "inherited", "inherited_from")}
        if any(
            not isinstance(value, list) or not all(isinstance(item, str) for item in value)
            for value in fields.values()
        ):
            raise ValueError("sensitivity metadata labels must be string arrays")
        result = cls(
            version,
            tuple(fields["explicit"]),
            tuple(fields["inherited"]),
            tuple(fields["inherited_from"]),
        )
        if payload["effective"] != list(result.effective):
            raise ValueError("sensitivity metadata effective labels are not canonical")
        return result

    @classmethod
    def from_json(cls, payload: str) -> SensitivityMetadata:
        return cls.from_payload(decode_canonical_json(payload))


__all__ = ("SensitivityMetadata",)
