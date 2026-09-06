"""Small provider-neutral release comparison for runtime capability values."""

from __future__ import annotations

import re
from dataclasses import dataclass

_RELEASE = re.compile(r"^(?P<release>[0-9]+(?:\.[0-9]+)*)(?P<suffix>.*)$")
_PRERELEASE = re.compile(
    r"^[._+-]?(?P<marker>dev|alpha|beta|rc|pre|a|b|c)(?P<number>[0-9]*)",
    re.IGNORECASE,
)
_PRERELEASE_RANK = {
    "dev": 0,
    "a": 1,
    "alpha": 1,
    "b": 2,
    "beta": 2,
    "c": 3,
    "pre": 3,
    "rc": 3,
}


@dataclass(frozen=True, slots=True)
class ComparableRelease:
    release: tuple[int, ...]
    prerelease: tuple[int, int] | None


def parse_comparable_release(value: str) -> ComparableRelease | None:
    """Parse the leading numeric release and recognized prerelease marker."""
    match = _RELEASE.match(value)
    if match is None:
        return None
    release = tuple(int(part) for part in match.group("release").split("."))
    suffix = match.group("suffix")
    prerelease_match = _PRERELEASE.match(suffix)
    prerelease: tuple[int, int] | None = None
    if prerelease_match is not None:
        marker = prerelease_match.group("marker").casefold()
        number_text = prerelease_match.group("number")
        prerelease = (_PRERELEASE_RANK[marker], int(number_text) if number_text else 0)
    return ComparableRelease(release, prerelease)


def compare_releases(left: str, right: str) -> int | None:
    """Compare runtime releases, ignoring non-prerelease vendor decoration."""
    parsed_left = parse_comparable_release(left)
    parsed_right = parse_comparable_release(right)
    if parsed_left is None or parsed_right is None:
        return None

    width = max(len(parsed_left.release), len(parsed_right.release))
    left_release = parsed_left.release + (0,) * (width - len(parsed_left.release))
    right_release = parsed_right.release + (0,) * (width - len(parsed_right.release))
    if left_release != right_release:
        return (left_release > right_release) - (left_release < right_release)

    if parsed_left.prerelease is None and parsed_right.prerelease is None:
        return 0
    if parsed_left.prerelease is None:
        return 1
    if parsed_right.prerelease is None:
        return -1
    return (parsed_left.prerelease > parsed_right.prerelease) - (
        parsed_left.prerelease < parsed_right.prerelease
    )
