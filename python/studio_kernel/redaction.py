"""Compatibility export for kernel consumers of the shared redaction helper."""

from studio_core.redaction import redact_sensitive_text

__all__ = ("redact_sensitive_text",)
