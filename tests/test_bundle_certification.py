import pytest

from studio_core.bundle_inventory import BundleInventory, BundleInventoryObject
from studio_storage import (
    BundleRoundTripError,
    assert_lossless_bundle_round_trip,
    compare_bundle_inventories,
)


def _inventory(*objects: BundleInventoryObject) -> BundleInventory:
    return BundleInventory(tuple(objects))


def test_bundle_round_trip_comparison_is_lossless_for_equal_inventory() -> None:
    before = _inventory(BundleInventoryObject("project", "project:p", "objects/project.json"))
    comparison = assert_lossless_bundle_round_trip(before, before)
    assert comparison.lossless is True
    assert comparison.before_digest == comparison.after_digest


def test_bundle_round_trip_reports_missing_and_changed_objects() -> None:
    before = _inventory(
        BundleInventoryObject("project", "project:p", "objects/project.json"),
        BundleInventoryObject("quality", "quality:q", "objects/quality.json"),
    )
    after = _inventory(
        BundleInventoryObject("project", "project:p", "objects/project-v2.json"),
        BundleInventoryObject("extra", "extra:x", "objects/extra.json"),
    )
    comparison = compare_bundle_inventories(before, after)
    assert comparison.missing == (("quality", "quality:q"),)
    assert comparison.added == (("extra", "extra:x"),)
    assert comparison.changed == (("project", "project:p"),)
    with pytest.raises(BundleRoundTripError):
        assert_lossless_bundle_round_trip(before, after)
