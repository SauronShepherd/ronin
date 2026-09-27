from __future__ import annotations

import pytest

from studio_data_engineering import export_sql_rows


def test_sql_editor_exports_bounded_escaped_csv() -> None:
    assert export_sql_rows(("id", "label"), ((1, "a,b"),)) == 'id,label\n1,"a,b"\n'


def test_sql_editor_export_rejects_row_and_byte_bounds() -> None:
    with pytest.raises(ValueError, match="max_rows"):
        export_sql_rows(("id",), ((1,), (2,)), max_rows=1)
    with pytest.raises(ValueError, match="max_bytes"):
        export_sql_rows(("id",), (("too-long",),), max_bytes=4)
