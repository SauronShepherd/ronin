from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from types import SimpleNamespace

import pytest
from studio_server.control_plane import (
    _decode_cursor,
    _encode_cursor,
    _etag,
    _finops_payload,
    _list_query,
    _page,
    _segments,
)


class _State(Enum):
    READY = "ready"


def test_control_plane_finops_payload_preserves_and_normalizes_values() -> None:
    metadata = {"source": "local"}
    record = SimpleNamespace(
        _internal="hidden",
        state=_State.READY,
        captured_at=datetime(2026, 10, 30, tzinfo=UTC),
        count=3,
        ratio=1.5,
        metadata=metadata,
        name="sample",
    )

    payload = _finops_payload(record)

    assert payload == {
        "state": "ready",
        "captured_at": "2026-10-30T00:00:00+00:00",
        "count": "3",
        "ratio": "1.5",
        "metadata": {"source": "local"},
        "name": "sample",
    }
    assert payload["metadata"] is not metadata


def test_control_plane_page_and_cursor_round_trip() -> None:
    first, cursor = _page(["a", "b", "c"], limit=2, offset=0)

    assert first == ["a", "b"]
    assert cursor == _encode_cursor(2)
    assert _decode_cursor(cursor) == 2
    assert _page(["a", "b", "c"], limit=2, offset=2) == (["c"], None)
    assert _decode_cursor(None) == 0


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        " cp1.MQ",
        "x" * 100,
        "cp2.MQ",
        "cp1.YQ",
        "cp1.w6k",
        "cp1.-MQ",
        "cp1.MDE",
        "cp1.é",
    ],
)
def test_control_plane_cursor_rejects_malformed_values(cursor: str) -> None:
    with pytest.raises(ValueError, match="cursor is invalid"):
        _decode_cursor(cursor)


def test_control_plane_list_query_decodes_page_parameters() -> None:
    assert _list_query("")[0] > 0
    assert _list_query(f"limit=2&cursor={_encode_cursor(5)}") == (2, 5)
    assert _segments("/v1/workspaces/%61") == ("v1", "workspaces", "a")
    assert _etag({"items": [1]}) == _etag({"items": [1]})


@pytest.mark.parametrize(
    "query",
    [
        "&limit=1",
        "cursor",
        "unknown=1",
        "limit=1&limit=2",
        "limit=nope",
        "limit=0",
        "limit=101",
        "cursor=bad",
    ],
)
def test_control_plane_list_query_rejects_invalid_parameters(query: str) -> None:
    with pytest.raises(ValueError, match=r".+"):
        _list_query(query)


def test_control_plane_path_rejects_empty_internal_segments() -> None:
    with pytest.raises(ValueError, match="empty segment"):
        _segments("/v1//workspaces")
