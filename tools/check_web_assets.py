"""Fail closed when the Studio shell references an unshipped relative asset."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

HTML_REFERENCE = re.compile(r"(?:src|href)=[\"']([^\"']+)[\"']")
MODULE_REFERENCE = re.compile(r"(?:import\s+(?:[^;]*?\s+from\s+)?|import\s*\()[\"']([^\"']+)[\"']")
CSS_URL_REFERENCE = re.compile(r"url\(\s*[\"']?([^\"')\s]+)[\"']?\s*\)")


def referenced_assets(root: Path) -> set[Path]:
    pending = [root / "index.html"]
    seen: set[Path] = set()
    assets: set[Path] = set()
    while pending:
        current = pending.pop()
        if current in seen or not current.is_file():
            continue
        seen.add(current)
        text = current.read_text(encoding="utf-8")
        matcher = (
            HTML_REFERENCE
            if current.suffix == ".html"
            else CSS_URL_REFERENCE
            if current.suffix == ".css"
            else MODULE_REFERENCE
        )
        for match in matcher.finditer(text):
            raw = match.group(1)
            parsed = urlsplit(raw)
            if parsed.scheme or parsed.netloc or raw.startswith(("#", "/", "data:")):
                continue
            target = (current.parent / parsed.path).resolve()
            assets.add(target)
            if target.suffix in {".html", ".js", ".css"}:
                pending.append(target)
    return assets


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "web").resolve()
    missing = sorted(path for path in referenced_assets(root) if not path.is_file())
    if missing:
        for path in missing:
            print(f"missing Studio asset: {path}", file=sys.stderr)
        return 1
    print(f"checked {len(referenced_assets(root))} Studio assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
