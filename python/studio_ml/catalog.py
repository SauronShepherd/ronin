"""Shared version bounds and parsing for persisted ML catalogs."""

from __future__ import annotations

MAX_CATALOG_VERSION = 2_147_483_647


def validate_catalog_version(value: object, catalog_name: str) -> int:
    """Require a positive version that fits PostgreSQL's INTEGER column."""
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= MAX_CATALOG_VERSION
    ):
        raise ValueError(
            f"{catalog_name} version must be between 1 and {MAX_CATALOG_VERSION}"
        )
    return value


def parse_catalog_version(value: str | int | None, catalog_name: str) -> int:
    """Parse canonical positive decimal path versions in the shared DB range."""
    if isinstance(value, int) and not isinstance(value, bool):
        parsed = value
    elif (
        isinstance(value, str)
        and value.isascii()
        and value.isdecimal()
        and not value.startswith("0")
    ):
        parsed = int(value)
    else:
        raise ValueError(
            f"{catalog_name} version must be a canonical positive decimal integer"
        )
    return validate_catalog_version(parsed, catalog_name)


__all__ = ("MAX_CATALOG_VERSION", "parse_catalog_version", "validate_catalog_version")
