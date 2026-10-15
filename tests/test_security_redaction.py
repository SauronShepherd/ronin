import pytest
from studio_security import redact


def test_redaction_is_recursive_and_never_leaks_secret_values():
    value = {"Authorization": "Bearer secret", "nested": [{"password": "p", "ok": "v"}]}
    result = redact(value)
    assert result == {
        "Authorization": "[REDACTED]",
        "nested": [{"password": "[REDACTED]", "ok": "v"}],
    }
    assert "secret" not in repr(result)


def test_redaction_bounds_nested_payloads():
    result = redact({"items": list(range(4))}, max_items=2)
    assert result["items"] == [0, 1]
    assert redact({"nested": {"secret": "value"}}, max_depth=1) == {"nested": "[TRUNCATED]"}


@pytest.mark.parametrize(
    "surface",
    ["logs", "errors", "traces", "evidence", "provider_metadata", "ui_payload"],
)
def test_secret_corpus_is_removed_from_every_output_surface(surface):
    marker = f"{surface}-secret-value"
    payload = {
        "message": "safe",
        "request": {"Authorization": f"Bearer {marker}", "trace": [{"client_secret": marker}]},
        "metadata": {"api_key": marker, "nested": {"private_key": marker}},
    }
    rendered = repr(redact(payload))
    assert marker not in rendered
    assert "[REDACTED]" in rendered


@pytest.mark.parametrize("key", ["PASSWORD", "ApiKey", "CLIENT_SECRET", "private_KEY"])
def test_redaction_matches_secret_terms_case_insensitively(key):
    marker = "case-variant-secret-value"
    result = redact({key: marker})
    assert result == {key: "[REDACTED]"}
    assert marker not in repr(result)


def test_redaction_truncates_nested_tuples_without_mutating_input():
    value = {"items": ("safe", {"token": "hidden"}, "ignored")}
    result = redact(value, max_depth=3, max_items=2)
    assert result == {"items": ["safe", {"token": "[REDACTED]"}]}
    assert value["items"][1]["token"] == "hidden"  # noqa: S105
