"""Installed CLI dispatcher adding the public evidence command without duplicating legacy commands."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from studio_cli import CliError, _client, main as _legacy_main
from studio_cli.network import ControlPlaneError


def _evidence(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="ronin evidence", description="show portable job evidence")
    parser.add_argument("job_id")
    parser.add_argument("--json", action="store_true")
    namespace = parser.parse_args(argv)
    try:
        items = _client().evidence(namespace.job_id)
    except (CliError, ControlPlaneError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for item in items:
        if namespace.json:
            print(json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            continue
        digest = item["digest"]
        digest_text = "-" if digest is None else str(digest)[:12]
        size = item["size_bytes"]
        print(
            f"{item['cell_id']}\t{item['role']}\t{item['availability']}\t"
            f"{digest_text}\t{size if size is not None else '-'}"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = tuple(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "evidence":
        return _evidence(args[1:])
    return _legacy_main(args)


__all__ = ("main",)
