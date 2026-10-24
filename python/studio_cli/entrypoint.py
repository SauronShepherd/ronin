"""Installed Ronin CLI entry point."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from studio_cli import main as _main


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch the single-operator Public CLI; identity providers are Ronin Pro."""

    return _main(tuple(sys.argv[1:] if argv is None else argv))


__all__ = ("main",)


if __name__ == "__main__":
    raise SystemExit(main())
