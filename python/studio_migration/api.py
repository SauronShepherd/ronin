"""Transport-neutral Migration Studio API router."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
from dataclasses import dataclass
from typing import cast
from urllib.parse import unquote

from .adapters.iics import IICS_ADAPTER_VERSION, discover_iics_zip
from .benchmark import BenchmarkResult, decide_promotion, promotion_evidence
from .blueprint import extract_blueprint
from .databricks import translate_notebook_job
from .dataiku import translate_code_recipes
from .fabric import translate_notebook_items
from .foundry import translate_python_functions
from .model import MigrationUnit, SourceArtifact, SourceInventory
from .profiles import discover_databricks, discover_dataiku, discover_fabric, discover_foundry
from .pyspark_codegen import export_migration_script
from .reports import render_validation_html, render_validation_markdown
from .session import MigrationSessionService
from .validation import CheckMode, ReportLevel

MAX_VALIDATION_ROWS = 100_000
MAX_VALIDATION_COLUMNS = 1_000
MAX_SOURCE_ARTIFACT_BYTES = 512 * 1024 * 1024

_PROFILE_DISCOVERERS = {
    "databricks": discover_databricks,
    "fabric": discover_fabric,
    "foundry": discover_foundry,
    "dataiku": discover_dataiku,
}
_PROFILE_TRANSLATORS = {
    "databricks": translate_notebook_job,
    "fabric": translate_notebook_items,
    "foundry": translate_python_functions,
    "dataiku": translate_code_recipes,
}


def _profile_inventory(profile: str, document: bytes, *, source_version: str) -> SourceInventory:
    """Convert a vendor report into the canonical session inventory contract."""

    try:
        report = _PROFILE_DISCOVERERS[profile](document, source_version=source_version)
    except KeyError as exc:
        raise ValueError("migration profile is unsupported") from exc
    states = {
        "unsupported": "unsupported",
        "partial": "review_required",
        "manual_decision": "review_required",
    }
    units = tuple(
        MigrationUnit(
            key=f"{item.source_type}:{item.source_id}",
            kind=item.source_type,
            name=item.source_id,
            state=states.get(item.status, "ready"),
            source_refs=(item.source_id,),
            notes=item.notes,
        )
        for item in report.objects
    )
    return SourceInventory(
        adapter_id=profile,
        adapter_version=report.importer_version,
        artifacts=(
            SourceArtifact(
                f"{profile}-inventory.json",
                hashlib.sha256(document).hexdigest(),
                len(document),
                "application/json",
            ),
        ),
        units=units,
    )


def _benchmark_from_payload(value: object, label: str) -> BenchmarkResult:
    if not isinstance(value, dict):
        raise ValueError(f"promote requires a {label} benchmark object")
    durations = value.get("durations_ms")
    if (
        not isinstance(value.get("name"), str)
        or not isinstance(value.get("warmup_runs"), int)
        or not isinstance(value.get("measured_runs"), int)
        or not isinstance(durations, list)
        or not isinstance(value.get("median_ms"), (int, float))
        or isinstance(value.get("median_ms"), bool)
        or not isinstance(value.get("fingerprint"), str)
        or not all(
            isinstance(item, (int, float)) and not isinstance(item, bool) for item in durations
        )
    ):
        raise ValueError(f"{label} benchmark has invalid fields")
    runtime_digest = value.get("runtime_build_fingerprint")
    if runtime_digest is not None and (
        not isinstance(runtime_digest, str) or not runtime_digest.strip()
    ):
        raise ValueError(f"{label} benchmark has invalid runtime build fingerprint")
    return BenchmarkResult(
        value["name"],
        value["warmup_runs"],
        value["measured_runs"],
        tuple(float(item) for item in durations),
        float(value["median_ms"]),
        value["fingerprint"],
        runtime_digest,
    )


MIGRATION_ROUTES = frozenset(
    {
        ("GET", "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/adapters"),
        ("GET", "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions"),
        ("POST", "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions"),
        (
            "GET",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}",
        ),
        (
            "POST",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/discover",
        ),
        (
            "PUT",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/scope",
        ),
        (
            "PUT",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/source-artifacts/{name}",
        ),
        (
            "PUT",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/blueprint",
        ),
        (
            "PUT",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/blueprint/{name}",
        ),
        (
            "POST",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/generate",
        ),
        (
            "POST",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/convert",
        ),
        (
            "GET",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/export",
        ),
        (
            "POST",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/qualify",
        ),
        (
            "POST",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/validate",
        ),
        (
            "POST",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/promote",
        ),
        (
            "GET",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/inventory",
        ),
        (
            "GET",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/blueprint-contract",
        ),
        (
            "GET",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/result",
        ),
        (
            "GET",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/findings",
        ),
        (
            "GET",
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}/qualification",
        ),
    }
)


@dataclass(frozen=True, slots=True)
class APIResponse:
    status: int
    payload: dict[str, object]


class MigrationAPIRouter:
    def __init__(self, service: MigrationSessionService) -> None:
        self.service = service

    def dispatch(
        self, method: str, path: str, payload: object | None = None, *, authorized: bool
    ) -> APIResponse:
        if not authorized:
            return APIResponse(
                401, {"error": {"code": "unauthorized", "message": "valid authorization required"}}
            )
        parts = tuple(unquote(part) for part in path.split("/") if part)
        if (
            len(parts) == 7
            and parts[:5] == ("v1", "workspaces", parts[2], "projects", parts[4])
            and parts[5:] == ("migration", "adapters")
        ):
            return APIResponse(
                200,
                {
                    "items": [
                        {
                            "adapter_id": "iics",
                            "adapter_version": IICS_ADAPTER_VERSION,
                            "capabilities": ["discover", "scope", "generate"],
                        },
                        *[
                            {
                                "adapter_id": profile,
                                "adapter_version": f"ronin-{profile}-0.1",
                                "capabilities": ["discover", "inventory"],
                            }
                            for profile in _PROFILE_DISCOVERERS
                        ],
                    ]
                },
            )
        if (
            len(parts) < 7
            or parts[:5] != ("v1", "workspaces", parts[2], "projects", parts[4])
            or parts[5] != "migration"
            or parts[6] != "sessions"
        ):
            return APIResponse(404, {"error": {"code": "not_found", "message": "route not found"}})
        workspace_id, project_id = parts[2], parts[4]
        if method == "POST" and len(parts) == 7:
            if payload not in (None, {}):
                return APIResponse(
                    400,
                    {
                        "error": {
                            "code": "invalid_request",
                            "message": "session creation body must be empty",
                        }
                    },
                )
            session = self.service.create(workspace_id, project_id)
            return APIResponse(201, session.to_payload())
        if method == "GET" and len(parts) == 7:
            snapshots = self.service.store_list(workspace_id, project_id)
            return APIResponse(200, {"items": list(snapshots)})
        if method == "GET" and len(parts) == 8:
            session_id = parts[7]
            try:
                session = self.service.get(session_id)
            except KeyError:
                return APIResponse(
                    404, {"error": {"code": "not_found", "message": "session not found"}}
                )
            if session.workspace_id != workspace_id or session.project_id != project_id:
                return APIResponse(
                    404, {"error": {"code": "not_found", "message": "session not found"}}
                )
            return APIResponse(200, session.to_payload())
        if len(parts) == 9 and method in {"GET", "POST", "PUT"}:
            session_id, operation = parts[7], parts[8]
            try:
                session = self.service.get(session_id)
            except KeyError:
                return APIResponse(
                    404, {"error": {"code": "not_found", "message": "session not found"}}
                )
            if session.workspace_id != workspace_id or session.project_id != project_id:
                return APIResponse(
                    404, {"error": {"code": "not_found", "message": "session not found"}}
                )
            try:
                if operation == "inventory" and method == "GET":
                    if session.inventory is None:
                        raise ValueError("session has no inventory")
                    return APIResponse(
                        200,
                        {
                            "adapter_id": session.inventory.adapter_id,
                            "adapter_version": session.inventory.adapter_version,
                            "digest": session.inventory.digest,
                            "artifacts": [
                                {
                                    "name": item.name,
                                    "digest": item.digest,
                                    "size_bytes": item.size_bytes,
                                    "media_type": item.media_type,
                                }
                                for item in session.inventory.artifacts
                            ],
                            "units": [
                                {
                                    "key": item.key,
                                    "kind": item.kind,
                                    "name": item.name,
                                    "state": item.state,
                                    "dependencies": list(item.dependencies),
                                    "source_refs": list(item.source_refs),
                                    "notes": list(item.notes),
                                }
                                for item in session.inventory.units
                            ],
                        },
                    )
                if operation == "blueprint-contract" and method == "GET":
                    if session.blueprint is None:
                        raise ValueError("session has no blueprint")
                    return APIResponse(
                        200,
                        {
                            "source_digest": session.blueprint.source_digest,
                            "digest": session.blueprint.digest,
                            "rules": [
                                {
                                    "rule_id": item.rule_id,
                                    "classification": item.classification,
                                    "evidence": item.evidence,
                                    "effect": item.effect,
                                }
                                for item in session.blueprint.rules
                            ],
                        },
                    )
                if operation == "result" and method == "GET":
                    return APIResponse(200, session.to_payload())
                if operation == "qualification" and method == "GET":
                    qualification = self.service.qualify_generated(session_id)
                    return APIResponse(200, qualification.to_payload())
                if operation == "export" and method == "GET":
                    project = self.service.generate(session_id)
                    script = export_migration_script(project)
                    return APIResponse(
                        200,
                        {
                            "filename": script.path,
                            "content": script.content,
                            "project_digest": project.project_digest,
                            "blueprint_digest": script.blueprint_digest,
                            "media_type": "text/x-python",
                        },
                    )
                if operation == "findings" and method == "GET":
                    qualification = self.service.qualify_generated(session_id)
                    return APIResponse(
                        200,
                        {
                            "status": qualification.status,
                            "findings": [item.to_payload() for item in qualification.findings],
                        },
                    )
                if operation == "discover" and method == "POST":
                    if isinstance(payload, dict) and "profile" in payload:
                        profile = payload.get("profile")
                        document_base64 = payload.get("document_base64")
                        source_version = payload.get("source_version", "unknown")
                        if (
                            not isinstance(profile, str)
                            or not isinstance(document_base64, str)
                            or not isinstance(source_version, str)
                        ):
                            raise ValueError(
                                "profile discovery requires profile, document_base64 "
                                "and source_version"
                            )
                        try:
                            document = base64.b64decode(document_base64, validate=True)
                        except (binascii.Error, ValueError) as exc:
                            raise ValueError("document_base64 is invalid") from exc
                        updated = self.service.discover(
                            session_id,
                            _profile_inventory(profile, document, source_version=source_version),
                        )
                    else:
                        if not isinstance(payload, dict) or not isinstance(
                            payload.get("archives"), list
                        ):
                            raise ValueError("discover requires an archives array")
                    archives: list[tuple[str, bytes]] = []
                    if "profile" not in payload:
                        for item in payload["archives"]:
                            if (
                                not isinstance(item, dict)
                                or not isinstance(item.get("name"), str)
                                or not isinstance(item.get("content_base64"), str)
                            ):
                                raise ValueError("each archive requires name and content_base64")
                            try:
                                content = base64.b64decode(item["content_base64"], validate=True)
                            except (binascii.Error, ValueError) as exc:
                                raise ValueError("archive content_base64 is invalid") from exc
                            archives.append((item["name"], content))
                        updated = self.service.discover(session_id, discover_iics_zip(archives))
                elif operation == "scope" and method == "PUT":
                    if (
                        not isinstance(payload, dict)
                        or not isinstance(payload.get("selected"), list)
                        or not all(isinstance(item, str) for item in payload["selected"])
                    ):
                        raise ValueError("scope requires a selected string array")
                    updated = self.service.set_scope(session_id, tuple(payload["selected"]))
                elif operation == "blueprint" and method == "PUT":
                    updated = self.service.set_blueprint(
                        session_id, extract_blueprint(json.dumps(payload, separators=(",", ":")))
                    )
                elif operation in {"generate", "convert"} and method == "POST":
                    if isinstance(payload, dict) and "profile" in payload:
                        profile = payload.get("profile")
                        document_base64 = payload.get("document_base64")
                        source_version = payload.get("source_version", "unknown")
                        if (
                            not isinstance(profile, str)
                            or not isinstance(document_base64, str)
                            or not isinstance(source_version, str)
                        ):
                            raise ValueError(
                                "profile conversion requires profile, document_base64 "
                                "and source_version"
                            )
                        try:
                            document = base64.b64decode(document_base64, validate=True)
                        except (binascii.Error, ValueError) as exc:
                            raise ValueError("document_base64 is invalid") from exc
                        try:
                            translator = _PROFILE_TRANSLATORS[profile]
                        except KeyError as exc:
                            raise ValueError("migration profile is unsupported") from exc
                        translation = translator(document, source_version=source_version)
                        return APIResponse(
                            200,
                            {
                                "profile": profile,
                                "workflow": json.loads(translation.workflow.to_json()),
                                "report": translation.report.to_payload(),
                                "report_digest": translation.report.digest,
                            },
                        )
                    project = self.service.generate(session_id)
                    return APIResponse(
                        200,
                        {
                            "project_digest": project.project_digest,
                            "inventory_digest": project.inventory_digest,
                            "scope_digest": project.scope_digest,
                            "blueprint_digest": project.blueprint_digest,
                            "manifest": json.loads(project.manifest),
                            "files": [
                                {"path": item.path, "content": item.content}
                                for item in project.files
                            ],
                        },
                    )
                elif operation == "qualify" and method == "POST":
                    qualification = self.service.qualify_generated(session_id)
                    return APIResponse(200, qualification.to_payload())
                elif operation == "validate" and method == "POST":
                    if not isinstance(payload, dict):
                        raise ValueError("validate requires an object payload")
                    expected = payload.get("expected")
                    actual = payload.get("actual")
                    if not isinstance(expected, list) or not isinstance(actual, list):
                        raise ValueError("validate requires expected and actual arrays")
                    if len(expected) > MAX_VALIDATION_ROWS or len(actual) > MAX_VALIDATION_ROWS:
                        raise ValueError(
                            f"validate result arrays exceed {MAX_VALIDATION_ROWS} rows"
                        )
                    if any(not isinstance(row, dict) for row in (*expected, *actual)):
                        raise ValueError("validate result rows must be objects")
                    if any(len(row) > MAX_VALIDATION_COLUMNS for row in (*expected, *actual)):
                        raise ValueError(f"validate rows exceed {MAX_VALIDATION_COLUMNS} columns")
                    asset_id = payload.get("asset_id", session_id)
                    level = payload.get("level", "simple")
                    modes = payload.get("modes", ["schema", "counts", "multiset"])
                    keys = payload.get("key_columns", [])
                    tolerances = payload.get("tolerances", {})
                    report_format = payload.get("format", "json")
                    if (
                        not isinstance(asset_id, str)
                        or not isinstance(level, str)
                        or not isinstance(modes, list)
                        or not isinstance(keys, list)
                        or not isinstance(tolerances, dict)
                        or not isinstance(report_format, str)
                    ):
                        raise ValueError("validate options have invalid types")
                    if report_format not in {"json", "markdown", "html"}:
                        raise ValueError("validate format must be json, markdown, or html")
                    if len(keys) > MAX_VALIDATION_COLUMNS:
                        raise ValueError("validate key_columns exceeds the column limit")
                    if any(not isinstance(key, str) or not key.strip() for key in keys) or len(
                        set(keys)
                    ) != len(keys):
                        raise ValueError("validate key_columns must be unique non-empty strings")
                    if any(
                        not isinstance(name, str)
                        or not name.strip()
                        or not isinstance(value, (int, float))
                        or isinstance(value, bool)
                        or not math.isfinite(float(value))
                        or value < 0
                        for name, value in tolerances.items()
                    ):
                        raise ValueError("validate tolerances must be finite non-negative numbers")
                    report = self.service.validate(
                        session_id,
                        expected,
                        actual,
                        asset_id=asset_id,
                        level=cast(ReportLevel, level),
                        modes=cast(tuple[CheckMode, ...], tuple(modes)),
                        key_columns=tuple(keys),
                        tolerances=tolerances,
                    )
                    result = json.loads(report.to_json())
                    if report_format == "json":
                        result["session"] = self.service.get(session_id).to_payload()
                        return APIResponse(200, result)
                    renderer = (
                        render_validation_markdown
                        if report_format == "markdown"
                        else render_validation_html
                    )
                    return APIResponse(
                        200,
                        {
                            "asset_id": report.asset_id,
                            "status": report.status,
                            "digest": report.digest,
                            "format": report_format,
                            "report": result,
                            "content": renderer(report),
                            "session": self.service.get(session_id).to_payload(),
                        },
                    )
                elif operation == "promote" and method == "POST":
                    if not isinstance(payload, dict):
                        raise ValueError("promote requires an object payload")
                    baseline = _benchmark_from_payload(payload.get("baseline"), "baseline")
                    candidate = _benchmark_from_payload(payload.get("candidate"), "candidate")
                    candidate_id = payload.get("candidate_id")
                    semantic_passed = payload.get("semantic_passed")
                    quality_passed = payload.get("quality_passed")
                    if not isinstance(candidate_id, str) or not candidate_id.strip():
                        raise ValueError("promote requires a non-empty candidate_id")
                    if not isinstance(semantic_passed, bool) or not isinstance(
                        quality_passed, bool
                    ):
                        raise ValueError("promote gates must be boolean")
                    ratio = payload.get("max_regression_ratio", 0.05)
                    if not isinstance(ratio, (int, float)) or isinstance(ratio, bool):
                        raise ValueError("max_regression_ratio must be numeric")
                    decision = decide_promotion(
                        candidate_id,
                        baseline=baseline,
                        candidate=candidate,
                        semantic_passed=semantic_passed,
                        quality_passed=quality_passed,
                        max_regression_ratio=float(ratio),
                    )
                    evidence = promotion_evidence(
                        decision,
                        baseline=baseline,
                        candidate=candidate,
                        semantic_passed=semantic_passed,
                        quality_passed=quality_passed,
                    )
                    session_snapshot = self.service.record_promotion(
                        session_id, evidence, promoted=decision.promoted
                    )
                    return APIResponse(
                        200,
                        {
                            "decision": decision.to_payload(),
                            "evidence": evidence,
                            "session": session_snapshot.to_payload(),
                        },
                    )
                else:
                    return APIResponse(
                        405,
                        {"error": {"code": "method_not_allowed", "message": "method not allowed"}},
                    )
            except (TypeError, ValueError) as exc:
                return APIResponse(400, {"error": {"code": "invalid_request", "message": str(exc)}})
            return APIResponse(200, updated.to_payload())
        if len(parts) == 10 and method == "PUT" and parts[8] == "blueprint":
            session_id, name = parts[7], parts[9]
            try:
                session = self.service.get(session_id)
                if session.workspace_id != workspace_id or session.project_id != project_id:
                    raise KeyError(session_id)
                if (
                    not name
                    or name in {".", ".."}
                    or "/" in name
                    or "\\" in name
                    or any(character.isspace() for character in name)
                ):
                    raise ValueError("blueprint name must be a path-safe token")
                if isinstance(payload, (bytes, bytearray, memoryview)):
                    document = bytes(payload)
                elif isinstance(payload, dict):
                    document = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                else:
                    raise ValueError("blueprint requires JSON or binary JSON content")
                updated = self.service.set_blueprint(session_id, extract_blueprint(document))
                return APIResponse(200, updated.to_payload())
            except (TypeError, ValueError) as exc:
                return APIResponse(400, {"error": {"code": "invalid_request", "message": str(exc)}})
        if len(parts) == 10 and method == "PUT" and parts[8] == "source-artifacts":
            session_id, name = parts[7], parts[9]
            try:
                session = self.service.get(session_id)
                if session.workspace_id != workspace_id or session.project_id != project_id:
                    raise KeyError(session_id)
                if (
                    not name
                    or name in {".", ".."}
                    or "/" in name
                    or "\\" in name
                    or name != name.strip()
                    or any(character.isspace() for character in name)
                ):
                    raise ValueError("source artifact name must be a path-safe token")
                if isinstance(payload, (bytes, bytearray, memoryview)):
                    content = bytes(payload)
                    media_type = "application/octet-stream"
                elif isinstance(payload, dict) and isinstance(payload.get("content_base64"), str):
                    try:
                        content = base64.b64decode(payload["content_base64"], validate=True)
                    except (binascii.Error, ValueError) as exc:
                        raise ValueError("source artifact content_base64 is invalid") from exc
                    media_type = payload.get("media_type", "application/octet-stream")
                else:
                    raise ValueError("source artifact requires binary content or content_base64")
                if len(content) > MAX_SOURCE_ARTIFACT_BYTES:
                    raise ValueError(f"source artifact exceeds {MAX_SOURCE_ARTIFACT_BYTES} bytes")
                if not isinstance(media_type, str) or not media_type.strip():
                    raise ValueError("source artifact media_type must be non-empty")
                updated = self.service.add_artifact(
                    session_id,
                    SourceArtifact(
                        name, hashlib.sha256(content).hexdigest(), len(content), media_type
                    ),
                )
                return APIResponse(200, updated.to_payload())
            except (KeyError, binascii.Error, ValueError) as exc:
                return APIResponse(400, {"error": {"code": "invalid_request", "message": str(exc)}})
        return APIResponse(
            405, {"error": {"code": "method_not_allowed", "message": "method not allowed"}}
        )


__all__ = ("APIResponse", "MIGRATION_ROUTES", "MigrationAPIRouter")
