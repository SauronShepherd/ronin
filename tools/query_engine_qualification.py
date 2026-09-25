"""Bounded qualification harness for the provider-neutral query contract.

The local result is a reference qualification only.  QueryFlux remains an
optional external provider and is reported as unavailable unless an external
qualification command is supplied by the operator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path


def qualify_local() -> dict[str, object]:
    import pyarrow as pa  # type: ignore[import-untyped]
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    from studio_data_engineering import QueryEngineRuntimeProvider
    from studio_query_engine import (
        DiscoveredEngine,
        EngineCapabilities,
        EngineHandshake,
        LocalSqlTransport,
        QueryExecutionPolicy,
        QueryRequest,
    )
    from studio_sql import DuckDbSqlEngine

    with tempfile.TemporaryDirectory(prefix="ronin-query-qualification-") as raw_dir:
        path = Path(raw_dir) / "rows.parquet"
        pq.write_table(pa.table({"category": ["a", "a", "b"]}), path)
        with DuckDbSqlEngine() as engine:
            engine.register_parquet("rows", str(path))
            transport = LocalSqlTransport(engine)
            provider = QueryEngineRuntimeProvider(
                DiscoveredEngine(
                    EngineHandshake(
                        "ronin-local-sql", "1", EngineCapabilities((("cancel", True),)), True
                    ),
                    ("duckdb",),
                    "ready",
                ),
                QueryExecutionPolicy(
                    (("qualification", ("duckdb",)),), required_capability="cancel"
                ),
            )
            provider.authorize(QueryRequest("SELECT 1", "qualification"), engine="duckdb")
            try:
                provider.authorize(QueryRequest("SELECT 1", "unauthorized"), engine="duckdb")
            except PermissionError:
                unauthorized_profile = "rejected"
            else:  # pragma: no cover - protects the qualification assertion
                unauthorized_profile = "accepted"
            handle, cursor = transport.submit(
                QueryRequest(
                    "SELECT category, count(*) AS n FROM rows GROUP BY category ORDER BY category",
                    "qualification",
                    max_rows=10,
                )
            )
            status, page, following = transport.poll(handle, cursor)
            rows = [list(row) for row in (page.rows if page is not None else ())]
            payload = {"columns": list(page.columns) if page else [], "rows": rows}
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            expected_digest = "2032c0cffe00f42b6cf39f776b036907ab6ed106530b415ca6965a64a3afcdc7"
            return {
                "status": "qualified"
                if status.state == "succeeded"
                and following is None
                and rows == [["a", 2], ["b", 1]]
                and digest == expected_digest
                else "failed",
                "provider": "ronin-local-sql",
                "query_state": status.state,
                "row_count": len(rows),
                "correctness_digest": digest,
                "expected_digest": expected_digest,
                "negative_cases": {"unauthorized_profile": unauthorized_profile},
            }


def qualify_external() -> dict[str, object]:
    command = os.environ.get("RONIN_QUERYFLUX_QUALIFICATION_COMMAND")
    if not command:
        return {"status": "not_configured", "provider": "queryflux", "command_configured": False}
    try:
        completed = subprocess.run(  # noqa: S603 - operator-supplied qualification command
            shlex.split(command, posix=os.name != "nt"),
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "failed",
            "provider": "queryflux",
            "command_configured": True,
            "error": type(exc).__name__,
        }
    if completed.returncode != 0:
        return {
            "status": "failed",
            "provider": "queryflux",
            "command_configured": True,
            "returncode": completed.returncode,
        }
    try:
        evidence = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "status": "failed",
            "provider": "queryflux",
            "command_configured": True,
            "error": "invalid_json",
        }
    if not isinstance(evidence, dict) or evidence.get("provider") != "queryflux":
        return {
            "status": "failed",
            "provider": "queryflux",
            "command_configured": True,
            "error": "invalid_provider_evidence",
        }
    result = dict(evidence)
    result["command_configured"] = True
    result["status"] = "qualified" if result.get("status") == "qualified" else "failed"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = {"local": qualify_local(), "queryflux": qualify_external()}
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
