from __future__ import annotations

from pathlib import Path


def test_security_policy_declares_private_reporting_and_scope() -> None:
    policy = (Path(__file__).parents[1] / "SECURITY.md").read_text(encoding="utf-8")
    required_sections = (
        "## Supported versions",
        "## Reporting a vulnerability",
        "## In-scope security boundaries",
        "## Safe-harbor expectations",
    )
    for section in required_sections:
        assert section in policy
    assert "Report a" in policy
    assert "vulnerability" in policy
    assert "Do not open a" in policy
    assert "public issue" in policy
    for sensitive_area in ("authentication", "tenant isolation", "SSRF", "artifact integrity"):
        assert sensitive_area in policy
