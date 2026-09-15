"""Dependency-free Prometheus text exposition for normalized metrics."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .contracts import MetricPoint

_NAME = re.compile(r"[^a-zA-Z0-9_:]")


def prometheus_text(points: Iterable[MetricPoint], *, max_points: int = 10_000) -> str:
    """Render bounded metrics deterministically as Prometheus exposition text."""
    selected = list(points)
    if len(selected) > max_points:
        raise ValueError("Prometheus export exceeds configured point limit")
    lines: list[str] = []
    for point in sorted(selected, key=lambda item: (item.name, item.attributes, item.observed_at)):
        name = _NAME.sub("_", point.name)
        if not name or not (name[0].isalpha() or name[0] == "_"):
            name = "ronin_" + name
        labels = ""
        if point.attributes:
            labels = "{" + ",".join(
                f'{_NAME.sub("_", key)}="{value.replace(chr(92), chr(92)+chr(92)).replace(chr(34), chr(92)+chr(34))}"'
                for key, value in point.attributes
            ) + "}"
        lines.append(f"{name}{labels} {point.value!r}")
    return "\n".join(lines) + ("\n" if lines else "")


__all__ = ["prometheus_text"]
