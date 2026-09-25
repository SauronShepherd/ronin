import pytest

from studio_data_engineering import (
    SparkConnectProvider,
    SparkConnectUnavailable,
)


class Row:
    def __init__(self, value):
        self.value = value

    def asDict(self, recursive=True):  # noqa: ARG002
        return {"value": self.value}


class DataFrame:
    def limit(self, _limit):
        return self

    def collect(self):
        return [Row(1), Row(2)]


class Session:
    def sql(self, _sql):
        return DataFrame()

    def stop(self):
        self.stopped = True


def test_spark_connect_provider_executes_sql_through_injected_session() -> None:
    provider = SparkConnectProvider("sc://localhost:15002", session_factory=lambda _: Session())
    result = provider.execute_sql("select 1", limit=10)
    assert result.rows == ({"value": 1}, {"value": 2})
    assert result.row_count == 2
    assert provider.handshake().provider == "spark-connect"


def test_spark_connect_provider_fails_with_actionable_missing_sdk(monkeypatch) -> None:
    provider = SparkConnectProvider("sc://localhost:15002")
    monkeypatch.setitem(__import__("sys").modules, "pyspark", None)
    with pytest.raises(SparkConnectUnavailable, match="pyspark is not installed"):
        provider._session()
