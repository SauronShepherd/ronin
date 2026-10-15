"""Command-line entry point for offline Performance Studio reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .renderer import render_report
from .service import analyze_performance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="performance-studio")
    parser.add_argument("run", type=Path, help="normalized run JSON")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--html", type=Path, help="write an accessible HTML report")
    args = parser.parse_args(argv)
    payload = {"run": json.loads(args.run.read_text(encoding="utf-8"))}
    if args.baseline:
        payload["baseline"] = json.loads(args.baseline.read_text(encoding="utf-8"))
    if args.policy:
        payload["policy"] = json.loads(args.policy.read_text(encoding="utf-8"))
    report = analyze_performance(payload)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.html:
        args.html.write_text(render_report(report), encoding="utf-8")
    return 0
