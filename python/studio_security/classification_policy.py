"""Fail-closed policy evaluation for classified catalog assets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Classification = Literal["public", "internal", "confidential", "restricted"]
_ORDER: dict[str, int] = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}


@dataclass(frozen=True)
class ClassificationPolicy:
    """Policy attached to an asset class, never inferred from a missing label."""

    maximum: Classification = "internal"
    explicit_high_sensitivity: bool = False

    def __post_init__(self) -> None:
        if self.maximum not in _ORDER:
            raise ValueError("unsupported classification")
        if not isinstance(self.explicit_high_sensitivity, bool):
            raise TypeError("explicit_high_sensitivity must be boolean")


@dataclass(frozen=True)
class ClassificationDecision:
    allowed: bool
    reason: str
    classification: str
    resource_ref: str


def evaluate_classification_policy(
    *,
    classification: str | None,
    resource_ref: str,
    policy: ClassificationPolicy,
    explicit_high_sensitivity_grant: bool = False,
) -> ClassificationDecision:
    """Evaluate classification before a provider or executor is invoked."""
    if (
        not resource_ref
        or resource_ref != resource_ref.strip()
        or any(char in resource_ref for char in "\x00\r\n")
        or classification is None
    ):
        return ClassificationDecision(
            False, "missing_classification", classification or "", resource_ref
        )
    label = classification.casefold()
    if label not in _ORDER:
        return ClassificationDecision(False, "unsupported_classification", label, resource_ref)
    if (
        label in {"confidential", "restricted"}
        and policy.explicit_high_sensitivity
        and not explicit_high_sensitivity_grant
    ):
        return ClassificationDecision(
            False, "explicit_high_sensitivity_grant_required", label, resource_ref
        )
    if _ORDER[label] > _ORDER[policy.maximum]:
        return ClassificationDecision(False, "classification_exceeds_policy", label, resource_ref)
    return ClassificationDecision(True, "classification_allowed", label, resource_ref)


__all__ = (
    "Classification",
    "ClassificationDecision",
    "ClassificationPolicy",
    "evaluate_classification_policy",
)
