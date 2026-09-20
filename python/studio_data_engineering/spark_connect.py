"""Optional Spark Connect runtime adapter.

The Spark dependency is imported lazily so local-preview and SDP workflows do
not require a Spark installation. SQL execution is deliberately explicit: the
compiler/SDP adapter is responsible for producing the SQL or DataFrame program.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .runtimes import RuntimeHandshake


class SparkConnectUnavailable(RuntimeError):
    """Spark Connect cannot be used in the current environment."""


@dataclass(frozen=True, slots=True)
class SparkConnectResult:
    rows: tuple[Mapping[str, object], ...]
    row_count: int
    endpoint: str


class SparkConnectProvider:
    def __init__(
        self, endpoint: str, *, session_factory: Callable[[str], Any] | None = None
    ) -> None:
        if not endpoint.strip():
            raise ValueError("Spark Connect endpoint must be non-empty")
        self.endpoint = endpoint
        self._session_factory = session_factory

    def handshake(self) -> RuntimeHandshake:
        return RuntimeHandshake(
            "spark-connect",
            "spark-connect",
            "4.x",
            frozenset({"batch", "stream", "dataframe", "logical-plan"}),
        )

    def execute_sql(self, sql: str, *, limit: int = 100) -> SparkConnectResult:
        if not sql.strip():
            raise ValueError("SQL must be non-empty")
        if limit < 1 or limit > 10_000:
            raise ValueError("limit must be between 1 and 10000")
        session = self._session()
        try:
            dataframe = session.sql(sql)
            rows = tuple(row.asDict(recursive=True) for row in dataframe.limit(limit).collect())
            return SparkConnectResult(rows, len(rows), self.endpoint)
        finally:
            stop = getattr(session, "stop", None)
            if callable(stop):
                stop()

    def _session(self) -> Any:
        if self._session_factory is not None:
            return self._session_factory(self.endpoint)
        try:
            from pyspark.sql import SparkSession
        except ImportError as exc:
            raise SparkConnectUnavailable(
                "pyspark is not installed; install the Spark Connect runtime extra"
            ) from exc
        try:
            return SparkSession.builder.remote(self.endpoint).getOrCreate()
        except Exception as exc:  # pragma: no cover - depends on external Spark service
            raise SparkConnectUnavailable(
                f"could not connect to Spark Connect endpoint {self.endpoint}"
            ) from exc


__all__ = ("SparkConnectProvider", "SparkConnectResult", "SparkConnectUnavailable")
