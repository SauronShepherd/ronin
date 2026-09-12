"""Pure workspace domain contracts for the Public v1 control plane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

WorkspaceState = Literal["active", "archived"]


def _require_text(value: str, field_name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be non-empty and trimmed")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{field_name} must not contain line breaks")


@dataclass(frozen=True, order=True, slots=True)
class WorkspaceId:
    """Stable workspace identity supplied by the application/persistence boundary."""

    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "workspace id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Workspace:
    """Durable top-level container for projects without provider-specific bindings."""

    id: WorkspaceId
    name: str
    description: str | None = None
    state: WorkspaceState = "active"

    def __post_init__(self) -> None:
        _require_text(self.name, "workspace name")
        if self.description is not None:
            _require_text(self.description, "workspace description")
        if self.state not in {"active", "archived"}:
            raise ValueError("workspace state must be active or archived")

    @property
    def archived(self) -> bool:
        return self.state == "archived"
