"""Installed Ronin CLI entry point."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence

from studio_cli import main as _main
from studio_cli.oidc_serve import serve_oidc_from_env


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch installed CLI commands, selecting OIDC serve only when explicitly requested."""

    args = tuple(sys.argv[1:] if argv is None else argv)
    if args != ("serve",):
        return _main(args)

    mode = os.environ.get("RONIN_AUTH_MODE", "static")
    if mode == "static":
        return _main(args)
    if mode != "oidc":
        print("error: RONIN_AUTH_MODE must be static or oidc", file=sys.stderr)
        return 2
    try:
        return serve_oidc_from_env()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


__all__ = ("main",)
