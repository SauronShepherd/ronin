"""Deterministic local qualification checks for migration translation fixtures."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from studio_core.portability import MigrationReport

from .analysis import Finding, analyze_pyspark
from .pyspark_codegen import GeneratedProject


@dataclass(frozen=True, slots=True)
class TranslationQualification:
    source_digest: str
    report_digest: str
    translated_objects: int
    unsupported_objects: int


@dataclass(frozen=True, slots=True)
class GeneratedQualification:
    project_digest: str
    files_checked: int
    findings: tuple[Finding, ...]
    status: str

    def to_payload(self) -> dict[str, object]:
        return {
            "project_digest": self.project_digest,
            "files_checked": self.files_checked,
            "status": self.status,
            "findings": [finding.to_payload() for finding in self.findings],
        }


def qualify_generated_project(project: GeneratedProject) -> GeneratedQualification:
    """Run credential-free syntax/static qualification over every generated file."""
    findings = tuple(
        finding for program in project.files for finding in analyze_pyspark(program.content)
    )
    status = "failed" if any(item.severity == "error" for item in findings) else "review_required"
    if not findings:
        status = "passed"
    return GeneratedQualification(project.project_digest, len(project.files), findings, status)


def qualify_fixture(
    source: str | bytes,
    discover: Callable[[str | bytes], MigrationReport],
    *,
    required_source_ids: Sequence[str] = (),
    translated_node_count: int | None = None,
) -> TranslationQualification:
    """Run deterministic, credential-free qualification checks on one fixture."""
    import hashlib

    report = discover(source)
    source_bytes = source.encode("utf-8") if isinstance(source, str) else source
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    ids = {item.source_id for item in report.objects}
    missing = set(required_source_ids) - ids
    if missing:
        raise ValueError(f"migration fixture report omits source objects: {sorted(missing)}")
    for item in report.objects:
        for note in item.notes:
            folded = note.casefold()
            if "password=" in folded or "bearer " in folded or "-----begin " in folded:
                raise ValueError("migration report contains credential material")
    translated = sum(item.status == "translated" for item in report.objects)
    unsupported = sum(item.status == "unsupported" for item in report.objects)
    if translated_node_count is not None and translated_node_count <= 0:
        raise ValueError("qualified fixture must expose at least one translated node")
    return TranslationQualification(source_digest, report.digest, translated, unsupported)


__all__ = (
    "GeneratedQualification",
    "TranslationQualification",
    "qualify_fixture",
    "qualify_generated_project",
)
