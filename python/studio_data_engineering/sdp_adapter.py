"""Boundary adapter for the existing SDP Studio project format.

The adapter is intentionally dependency-free. YAML parsing and actual SDP
compilation belong to the optional SDP Studio provider; Ronin owns identity,
artifact references and execution governance.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SdpProjectSource:
    project_name: str
    project_yaml: bytes
    pipeline_documents: tuple[tuple[str, bytes], ...]

    def __post_init__(self) -> None:
        if not self.project_name.strip():
            raise ValueError("project_name must be non-empty")
        if not self.project_yaml:
            raise ValueError("project_yaml must not be empty")
        names = [name for name, _ in self.pipeline_documents]
        if len(names) != len(set(names)):
            raise ValueError("pipeline document names must be unique")

    @property
    def source_digest(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.project_yaml)
        for name, payload in sorted(self.pipeline_documents):
            digest.update(name.encode("utf-8"))
            digest.update(payload)
        return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class SdpImportReport:
    source_digest: str
    artifact_names: tuple[str, ...]
    lossless: bool
    diagnostics: tuple[str, ...] = ()
    loss_report: tuple[Mapping[str, str], ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "source_digest": self.source_digest,
            "artifact_names": list(self.artifact_names),
            "lossless": self.lossless,
            "diagnostics": list(self.diagnostics),
            "loss_report": [dict(item) for item in self.loss_report],
        }


class SdpStudioProvider:
    """Provider-neutral façade around SDP Studio.

    ``validate`` and ``generate`` are intentionally explicit extension points:
    a real installed SDP Studio provider can implement them without changing
    Ronin's project/job/artifact contracts.
    """

    provider_id = "sdp-studio"
    provider_version = "0.1"

    def __init__(
        self, command: Sequence[str] | None = None, *, timeout_seconds: float = 60.0
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.command = tuple(command) if command is not None else None
        self.timeout_seconds = timeout_seconds

    def import_project(self, source: SdpProjectSource) -> SdpImportReport:
        names = (".sdpstudio/project.yaml",) + tuple(
            name for name, _ in source.pipeline_documents
        )
        return SdpImportReport(source.source_digest, names, lossless=True)

    def validate(
        self, source: SdpProjectSource, *, compiled: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        report = self.import_project(source)
        if compiled is None and self.command is not None:
            compiled = self._invoke("validate", source)
        if compiled is None:
            return {
                "provider": self.provider_id,
                "source_digest": report.source_digest,
                "status": "provider_required",
                "lossless": report.lossless,
                "diagnostics": ["install or configure the SDP Studio compiler"],
                "loss_report": report.to_payload()["loss_report"],
            }
        return {
            "provider": self.provider_id,
            "source_digest": report.source_digest,
            "status": "valid" if compiled.get("valid", False) else "invalid",
            "lossless": report.lossless,
            "compiled": dict(compiled),
            "loss_report": report.to_payload()["loss_report"],
        }

    def compile(self, source: SdpProjectSource) -> dict[str, object]:
        """Invoke the configured SDP Studio CLI and return its JSON result."""
        if self.command is None:
            raise RuntimeError("SDP Studio provider command is not configured")
        return self._invoke("compile", source)

    def _invoke(self, action: str, source: SdpProjectSource) -> dict[str, object]:
        payload = {
            "action": action,
            "project_name": source.project_name,
            "project_yaml": source.project_yaml.decode("utf-8"),
            "pipeline_documents": [
                {"name": name, "content": content.decode("utf-8")}
                for name, content in source.pipeline_documents
            ],
        }
        try:
            completed = subprocess.run(  # noqa: S603 - command is explicit provider config
                list(self.command),
                input=json.dumps(payload, sort_keys=True),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"SDP Studio provider unavailable: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or "provider exited with failure"
            raise RuntimeError(f"SDP Studio provider failed: {detail}")
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("SDP Studio provider returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise RuntimeError("SDP Studio provider result must be an object")
        return result

    def generated_artifact_names(self, source: SdpProjectSource) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    "transformations/generated.py",
                    "spark-pipeline.yaml",
                    "ronin/sdp-source-digest.txt",
                }
                | {name.removeprefix(".sdpstudio/") for name, _ in source.pipeline_documents}
            )
        )


__all__ = ("SdpImportReport", "SdpProjectSource", "SdpStudioProvider")
