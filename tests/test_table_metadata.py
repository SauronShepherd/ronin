from __future__ import annotations

import pytest
from studio_lakehouse import OpenTableField, OpenTableIdentifier, TableMetadata


def test_table_metadata_keeps_identity_independent_from_physical_location() -> None:
    identifier = OpenTableIdentifier(("analytics",), "events")
    first = TableMetadata(
        identifier,
        "delta",
        "s3://warehouse/a",
        True,
        (OpenTableField("id", "int", False), OpenTableField("day", "date", True)),
        ("day",),
    )
    second = TableMetadata(
        identifier,
        "delta",
        "s3://warehouse/b",
        True,
        first.schema,
        first.partition_spec,
    )
    assert first.identifier == second.identifier
    assert first.location != second.location
    assert first.identity != second.identity


def test_table_metadata_rejects_unknown_partition_field() -> None:
    with pytest.raises(ValueError, match="must exist"):
        TableMetadata(
            OpenTableIdentifier(("analytics",), "events"),
            "iceberg",
            "file:///warehouse/events",
            False,
            (OpenTableField("id", "int", False),),
            ("missing",),
        )


def test_table_metadata_has_strict_canonical_round_trip() -> None:
    metadata = TableMetadata(
        OpenTableIdentifier(("analytics",), "events"),
        "iceberg",
        "file:///warehouse/events",
        False,
        (OpenTableField("id", "int", False),),
    )
    assert TableMetadata.from_json(metadata.to_json()) == metadata
    invalid = metadata.to_data()
    invalid["extra"] = True
    with pytest.raises(ValueError, match="invalid shape"):
        TableMetadata.from_data(invalid)


def test_table_metadata_rejects_empty_property_keys_or_values() -> None:
    identifier = OpenTableIdentifier(("analytics",), "events")
    fields = (OpenTableField("id", "int", False),)
    for properties in ((("", "value"),), (("owner", ""),), ((" owner", "value"),)):
        with pytest.raises(ValueError, match="properties"):
            TableMetadata(
                identifier, "delta", "s3://warehouse/events", True, fields, (), properties
            )
