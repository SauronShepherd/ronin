from __future__ import annotations

from tools.query_engine_qualification import qualify_external, qualify_local


def test_local_query_engine_qualification_is_bounded_and_deterministic() -> None:
    result = qualify_local()
    assert result["status"] == "qualified"
    assert result["query_state"] == "succeeded"
    assert result["correctness_digest"] == result["expected_digest"]
    assert result["row_count"] == 2
    assert result["negative_cases"] == {"unauthorized_profile": "rejected"}


def test_queryflux_qualification_is_explicitly_unconfigured_without_operator_input(
    monkeypatch,
) -> None:
    monkeypatch.delenv("RONIN_QUERYFLUX_QUALIFICATION_COMMAND", raising=False)
    result = qualify_external()
    assert result == {
        "status": "not_configured",
        "provider": "queryflux",
        "command_configured": False,
    }
