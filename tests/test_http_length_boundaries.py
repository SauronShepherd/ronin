from __future__ import annotations

import pytest
from studio_server.http import _submit_project


def test_project_name_accepts_declared_256_character_boundary() -> None:
    value = "p" * 256

    assert _submit_project({"project": value}) == value


def test_project_name_rejects_one_character_over_declared_boundary() -> None:
    with pytest.raises(ValueError, match="at most 256"):
        _submit_project({"project": "p" * 257})
