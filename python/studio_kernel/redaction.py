"""Defensive redaction helpers for operational kernel evidence."""

from __future__ import annotations

import re

_NAMED_SECRET_PATTERN = re.compile(
    r"(?ix)([\"']?[\w.-]*(?:token|secret|password|passwd|api[_-]?key)[\w.-]*[\"']?\s*[:=]\s*[\"']?)"
    r"([^\s,\"';}]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)(\bbearer\s+)([^\s,;]+)")
_URI_CREDENTIAL_PATTERN = re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s/@]+)(@)")
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}(?:\.[A-Za-z0-9_-]+)?\b")
_PROVIDER_TOKEN_PATTERN = re.compile(
    r"\b(?:AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{16,}|xox[bp]-[A-Za-z0-9-]{10,})\b"
)
_PEM_PATTERN = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)


def redact_sensitive_text(value: object) -> str:
    """Redact common credentials in operational text as defense in depth."""
    text = str(value)
    text = _PEM_PATTERN.sub("[REDACTED PRIVATE KEY]", text)
    text = _NAMED_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
    text = _BEARER_PATTERN.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
    text = _URI_CREDENTIAL_PATTERN.sub(
        lambda match: f"{match.group(1)}[REDACTED]{match.group(3)}",
        text,
    )
    text = _JWT_PATTERN.sub("[REDACTED]", text)
    return _PROVIDER_TOKEN_PATTERN.sub("[REDACTED]", text)
