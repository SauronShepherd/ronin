import pytest

from studio_query_engine import EngineCapabilities, QueryExecutionPolicy, QueryRequest


def test_query_policy_requires_explicit_profile_engine_and_capability() -> None:
    policy = QueryExecutionPolicy((("local", ("duckdb",)),), required_capability="cancel")
    request = QueryRequest("SELECT 1", "local")

    assert (
        policy.select_engine(
            request,
            engine="duckdb",
            capabilities=EngineCapabilities((("cancel", True),)),
        )
        == "duckdb"
    )


@pytest.mark.parametrize(
    ("query_request", "engine", "capabilities", "message"),
    [
        (QueryRequest("SELECT 1", "unknown"), "duckdb", EngineCapabilities(()), "profile"),
        (QueryRequest("SELECT 1", "local"), "trino", EngineCapabilities(()), "engine"),
        (QueryRequest("SELECT 1", "local"), "duckdb", EngineCapabilities(()), "capability"),
        (
            QueryRequest("SELECT 1", "local", "strict"),
            "duckdb",
            EngineCapabilities((("cancel", True),)),
            "strict",
        ),
        (
            QueryRequest("SELECT 1", "local", "best_effort"),
            "duckdb",
            EngineCapabilities((("cancel", True),)),
            "translation",
        ),
    ],
)
def test_query_policy_fails_closed(
    query_request: QueryRequest,
    engine: str,
    capabilities: EngineCapabilities,
    message: str,
) -> None:
    policy = QueryExecutionPolicy((("local", ("duckdb",)),), required_capability="cancel")
    with pytest.raises(PermissionError, match=message):
        policy.select_engine(query_request, engine=engine, capabilities=capabilities)


@pytest.mark.parametrize("value", [" profile", "profile ", "profile\nunsafe", "profile\x00unsafe"])
def test_query_policy_rejects_ambiguous_profile_identifiers(value: str) -> None:
    with pytest.raises(ValueError, match="query profile"):
        QueryExecutionPolicy(((value, ("duckdb",)),))
