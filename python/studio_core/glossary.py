"""Provider-neutral glossary contracts for Public v1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json


def _text(value: str, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(c in value for c in "\r\n\x00")
    ):
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


@dataclass(frozen=True, order=True, slots=True)
class GlossaryTermId:
    value: str

    def __post_init__(self) -> None:
        _text(self.value, "glossary term id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class GlossaryTerm:
    id: GlossaryTermId
    version: str
    name: str
    definition: str
    owner: str
    references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.version, "glossary term version"),
            (self.name, "glossary term name"),
            (self.definition, "glossary term definition"),
            (self.owner, "glossary term owner"),
        ):
            _text(value, name)
        refs = tuple(_text(ref, "glossary term reference") for ref in self.references)
        if len(refs) != len(set(refs)):
            raise ValueError("glossary term references must be unique")
        object.__setattr__(self, "references", tuple(sorted(refs)))

    def to_payload(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "version": self.version,
            "name": self.name,
            "definition": self.definition,
            "owner": self.owner,
            "references": list(self.references),
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> GlossaryTerm:
        keys = {"id", "version", "name", "definition", "owner", "references"}
        if not isinstance(payload, Mapping) or set(payload) != keys:
            raise ValueError("glossary term has invalid shape")
        values = [payload[key] for key in ("id", "version", "name", "definition", "owner")]
        refs = payload["references"]
        if (
            not all(isinstance(value, str) for value in values)
            or not isinstance(refs, list)
            or not all(isinstance(ref, str) for ref in refs)
        ):
            raise ValueError("glossary term payload has invalid types")
        return cls(
            GlossaryTermId(cast(str, payload["id"])),
            cast(str, payload["version"]),
            cast(str, payload["name"]),
            cast(str, payload["definition"]),
            cast(str, payload["owner"]),
            tuple(cast(str, ref) for ref in refs),
        )

    @classmethod
    def from_json(cls, payload: str) -> GlossaryTerm:
        return cls.from_payload(decode_canonical_json(payload.encode("utf-8")))
