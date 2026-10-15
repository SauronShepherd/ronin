"""Small reproducible benchmark for the host-neutral AI Studio gateway."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def run(iterations: int) -> dict[str, float | int]:
    started = time.perf_counter()
    for _ in range(iterations):
        # The real benchmark injects an HTTP/runtime transport here. This baseline
        # measures harness overhead and is intentionally deterministic.
        json.dumps({"model": "benchmark", "messages": []}, separators=(",", ":"))
    elapsed = time.perf_counter() - started
    return {
        "iterations": iterations,
        "elapsed_seconds": elapsed,
        "requests_per_second": iterations / elapsed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    result = run(args.iterations)
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
