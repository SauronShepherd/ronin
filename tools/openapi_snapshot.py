"""Verify the deterministic hash of the public OpenAPI snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def canonical_digest(document: Path) -> str:
    value = json.loads(document.read_text(encoding="utf-8"))
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def check(document: Path, snapshot: Path) -> str:
    digest = canonical_digest(document)
    expected = snapshot.read_text(encoding="utf-8").strip()
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise ValueError("OpenAPI snapshot must contain one lowercase SHA-256 digest")
    if digest != expected:
        raise ValueError(f"OpenAPI snapshot mismatch: expected {expected}, got {digest}")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("document", type=Path, default=Path("api/openapi-v1.json"), nargs="?")
    parser.add_argument("snapshot", type=Path, default=Path("api/openapi-v1.sha256"), nargs="?")
    args = parser.parse_args()
    print(check(args.document, args.snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
