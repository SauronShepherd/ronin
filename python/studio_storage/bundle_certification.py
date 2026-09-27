"""Fail-closed certification helpers for native Ronin Bundle round-trips."""

from __future__ import annotations

from dataclasses import dataclass

from studio_core.bundle_inventory import BundleInventory


@dataclass(frozen=True, slots=True)
class BundleRoundTripComparison:
    before_digest: str
    after_digest: str
    missing: tuple[tuple[str, str], ...] = ()
    added: tuple[tuple[str, str], ...] = ()
    changed: tuple[tuple[str, str], ...] = ()

    @property
    def lossless(self) -> bool:
        return not self.missing and not self.added and not self.changed

    def to_payload(self) -> dict[str, object]:
        return {
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
            "missing": [list(item) for item in self.missing],
            "added": [list(item) for item in self.added],
            "changed": [list(item) for item in self.changed],
            "lossless": self.lossless,
        }


class BundleRoundTripError(ValueError):
    """Raised when a native Bundle re-export is not semantically lossless."""


def compare_bundle_inventories(
    before: BundleInventory, after: BundleInventory
) -> BundleRoundTripComparison:
    before_by_key = {item.key: item for item in before.objects}
    after_by_key = {item.key: item for item in after.objects}
    missing = tuple(sorted(set(before_by_key) - set(after_by_key)))
    added = tuple(sorted(set(after_by_key) - set(before_by_key)))
    changed = tuple(
        sorted(
            key
            for key in set(before_by_key) & set(after_by_key)
            if before_by_key[key] != after_by_key[key]
        )
    )
    return BundleRoundTripComparison(before.digest, after.digest, missing, added, changed)


def assert_lossless_bundle_round_trip(
    before: BundleInventory, after: BundleInventory
) -> BundleRoundTripComparison:
    comparison = compare_bundle_inventories(before, after)
    if not comparison.lossless:
        raise BundleRoundTripError(comparison.to_payload())
    return comparison


__all__ = (
    "BundleRoundTripComparison",
    "BundleRoundTripError",
    "assert_lossless_bundle_round_trip",
    "compare_bundle_inventories",
)
