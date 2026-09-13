from studio_lakehouse import OpenTableField, OpenTableIdentifier, OpenTableState


def test_open_table_identifier_is_stable_and_qualified() -> None:
    identifier = OpenTableIdentifier(("analytics", "sales"), "orders")
    assert identifier.qualified_name == "analytics.sales.orders"


def test_open_table_state_canonicalizes_properties() -> None:
    state = OpenTableState(
        "iceberg",
        OpenTableIdentifier(("analytics",), "orders"),
        "s3://warehouse/analytics/orders",
        "123",
        (OpenTableField("id", "int64", False),),
        (("write.format.default", "parquet"), ("owner", "data")),
    )
    assert state.properties == (
        ("owner", "data"),
        ("write.format.default", "parquet"),
    )
