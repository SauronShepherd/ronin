from __future__ import annotations

import pytest
from studio_data_engineering.result_paging import page_query_result


def test_pages_are_stable_and_cursor_is_bound_to_the_result_digest() -> None:
    rows = [[1], [2], [3]]
    first = page_query_result(columns=["id"], rows=rows, digest="a" * 64, page_size=2)
    assert first["columns"] == ["id"]
    assert first["rows"] == [[1], [2]]
    assert first["row_count"] == 3
    cursor = first["next_cursor"]
    assert isinstance(cursor, str)
    assert cursor

    second = page_query_result(
        columns=["id"], rows=rows, digest="a" * 64, cursor=cursor, page_size=2
    )
    assert second == {
        "columns": ["id"],
        "rows": [[3]],
        "row_count": 3,
        "next_cursor": None,
    }

    with pytest.raises(ValueError, match="does not match"):
        page_query_result(columns=["id"], rows=rows, digest="b" * 64, cursor=cursor)


@pytest.mark.parametrize("page_size", [0, -1, 10_001, True, "2"])
def test_page_size_must_be_a_bounded_integer(page_size: object) -> None:
    with pytest.raises(ValueError, match="page_size"):
        page_query_result(columns=["id"], rows=[[1]], digest="a" * 64, page_size=page_size)  # type: ignore[arg-type]


@pytest.mark.parametrize("cursor", ["!", "", "eyJkaWdlc3QiOiJhIn0"])
def test_invalid_cursors_fail_closed(cursor: str) -> None:
    with pytest.raises(ValueError, match="cursor"):
        page_query_result(columns=["id"], rows=[[1], [2]], digest="a" * 64, cursor=cursor)


def test_rows_must_match_the_persisted_column_shape() -> None:
    with pytest.raises(ValueError, match="width"):
        page_query_result(columns=["id"], rows=[[1, 2]], digest="a" * 64)


def test_result_digest_must_be_a_lowercase_sha256() -> None:
    with pytest.raises(ValueError, match="digest"):
        page_query_result(columns=["id"], rows=[], digest="z" * 64)
