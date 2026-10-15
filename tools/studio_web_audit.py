"""Static quality gates and budgets for the modular Studio web surface."""

from __future__ import annotations

import json
import re
from pathlib import Path

WEB = Path("web")
MAX_LINES = 400
ALLOWED = {".html", ".css", ".js", ".mjs", ".json", ".png", ".webp", ".svg"}
TEXT_EXTENSIONS = {".html", ".css", ".js", ".mjs", ".json"}


def audit() -> dict[str, object]:
    files = [path for path in WEB.rglob("*") if path.is_file()]
    text_files = [path for path in files if path.suffix in TEXT_EXTENSIONS]
    failures: list[str] = []
    for path in files:
        if path.suffix not in ALLOWED and path.name != "README.md":
            failures.append(f"unsupported asset extension: {path}")
    for path in text_files:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            failures.append(f"{path} has {len(lines)} lines; maximum is {MAX_LINES}")
        if "data:image/png;base64" in path.read_text(encoding="utf-8"):
            failures.append(f"embedded PNG data URI remains in {path}")
    index = (WEB / "index.html").read_text(encoding="utf-8")
    required = ('meta name="description"', 'script type="module"', 'id="view"', 'id="main"')
    for marker in required:
        if marker not in index:
            failures.append(f"index.html missing {marker}")
    js = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (WEB / "js").rglob("*")
        if path.is_file() and path.suffix in {".js", ".mjs"}
    )
    for forbidden in ("providerCandidates", "Neo4j", "PuppyGraph", "GraphFrames"):
        if forbidden in js:
            failures.append(f"invented provider data remains: {forbidden}")
    result = {
        "files": len(files),
        "text_bytes": sum(path.stat().st_size for path in text_files),
        "asset_bytes": sum(path.stat().st_size for path in files),
        "module_count": len(
            [
                path
                for path in (WEB / "js").rglob("*")
                if path.is_file() and path.suffix in {".js", ".mjs"}
            ]
        ),
        "route_invocations": len(re.findall(r"/v1/", js)),
        "failures": failures,
    }
    if failures:
        raise SystemExit(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    audit()
