"""Measure and ratchet the Studio's static delivery budget."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

WEB = Path("web")
BASELINE = Path("docs/ui/web-budget.json")
TEXT_EXTENSIONS = {".css", ".html", ".js"}


def _size(path: Path) -> int:
    raw = path.read_bytes()
    if path.suffix in TEXT_EXTENSIONS:
        return len(raw.replace(b"\r\n", b"\n"))
    return len(raw)


def measure() -> dict[str, int]:
    assets = [p for p in WEB.rglob("*") if p.is_file() and p.name != "README.md"]
    return {
        "asset_bytes": sum(_size(p) for p in assets),
        "asset_requests": len(assets),
        "module_requests": len(list((WEB / "js").rglob("*.js"))),
        "stylesheet_requests": len(list((WEB / "styles").rglob("*.css"))),
        "html_bytes": _size(WEB / "index.html"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()
    current = measure()
    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    if args.check:
        if not BASELINE.exists():
            raise SystemExit(f"missing measured baseline: {BASELINE}")
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        regressions = {
            key: (baseline[key], current[key]) for key in current if current[key] > baseline[key]
        }
        if regressions:
            raise SystemExit("Studio budget regressed: " + json.dumps(regressions, sort_keys=True))
    print(json.dumps(current, indent=2))


if __name__ == "__main__":
    main()
