"""Stable cursors for bounded, immutable QueryFlux result pages."""

from __future__ import annotations

import base64
import json
import re

from studio_query_engine import MAX_RESULT_BYTES

_CURSOR_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,256}\Z")
_MAX_PAGE_SIZE = 10_000
_PAGE_RESPONSE_OVERHEAD_BYTES = 512


def encode_result_cursor(*, digest: str, offset: int) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("result cursor digest is invalid")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 1:
        raise ValueError("result cursor offset must be a positive integer")
    raw = json.dumps(
        {"digest": digest, "offset": offset, "version": 1},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_result_cursor(value: str, *, digest: str, row_count: int) -> int:
    if not isinstance(value, str) or not _CURSOR_PATTERN.fullmatch(value):
        raise ValueError("result cursor is invalid")
    try:
        payload = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("result cursor is invalid") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"digest", "offset", "version"}
        or payload.get("version") != 1
        or payload.get("digest") != digest
    ):
        raise ValueError("result cursor does not match this immutable result")
    offset = payload.get("offset")
    if isinstance(offset, bool) or not isinstance(offset, int) or not 1 <= offset < row_count:
        raise ValueError("result cursor offset is outside this result")
    if encode_result_cursor(digest=digest, offset=offset) != value:
        raise ValueError("result cursor is not in canonical form")
    return offset


def page_query_result(
    *,
    columns: object,
    rows: object,
    digest: str,
    cursor: str | None = None,
    page_size: int = 1_000,
) -> dict[str, object]:
    """Return a deterministic page from a validated content-addressed result."""

    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= _MAX_PAGE_SIZE
    ):
        raise ValueError("page_size must be between 1 and 10000")
    if not isinstance(columns, list) or any(not isinstance(name, str) for name in columns):
        raise ValueError("stored result columns are invalid")
    if not isinstance(rows, list) or any(not isinstance(row, list) for row in rows):
        raise ValueError("stored result rows are invalid")
    if any(len(row) != len(columns) for row in rows):
        raise ValueError("stored result row width does not match columns")
    offset = (
        0 if cursor is None else decode_result_cursor(cursor, digest=digest, row_count=len(rows))
    )
    selected: list[list[object]] = []
    end = offset
    while end < len(rows) and len(selected) < page_size:
        candidate_end = end + 1
        next_cursor = (
            encode_result_cursor(digest=digest, offset=candidate_end)
            if candidate_end < len(rows)
            else None
        )
        candidate = {
            "columns": columns,
            "rows": [*selected, rows[end]],
            "row_count": len(rows),
            "next_cursor": next_cursor,
        }
        try:
            encoded = json.dumps(
                candidate,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("stored query result is not JSON-safe") from exc
        if len(encoded) > MAX_RESULT_BYTES + _PAGE_RESPONSE_OVERHEAD_BYTES:
            if not selected:
                raise ValueError("one result row exceeds the maximum page byte budget")
            break
        selected.append(rows[end])
        end = candidate_end
    next_cursor = encode_result_cursor(digest=digest, offset=end) if end < len(rows) else None
    return {
        "columns": columns,
        "rows": selected,
        "row_count": len(rows),
        "next_cursor": next_cursor,
    }


__all__ = ("decode_result_cursor", "encode_result_cursor", "page_query_result")
