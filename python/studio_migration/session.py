"""Application-level Migration Studio session lifecycle."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Literal, cast

from .blueprint import BlueprintContract, BlueprintRule, RuleClass
from .model import MigrationUnit, ObjectState, ScopeSelection, SourceArtifact, SourceInventory
from .pyspark_codegen import GeneratedProject, generate_project
from .qualification import GeneratedQualification, qualify_generated_project
from .scope import select_scope
from .validation import CheckMode, ReportLevel, ValidationReport, validate_results

SessionState = Literal[
    "draft",
    "artifacts_ready",
    "discovering",
    "scope_ready",
    "converting",
    "qualifying",
    "completed",
    "failed",
    "cancelled",
]

MAX_SESSION_ARTIFACTS = 256
MAX_SESSION_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class MigrationSession:
    id: str
    workspace_id: str
    project_id: str
    state: SessionState = "draft"
    inventory: SourceInventory | None = None
    selection: ScopeSelection | None = None
    blueprint: BlueprintContract | None = None
    result_digest: str | None = None
    generated_manifest_digest: str | None = None
    generated_file_digests: tuple[tuple[str, str], ...] = ()
    import_digest: str | None = None
    import_status: str | None = None
    validation_digest: str | None = None
    validation_status: str | None = None
    promotion_digest: str | None = None
    promotion_status: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "state": self.state,
            "inventory_digest": self.inventory.digest if self.inventory else None,
            "scope_digest": self.selection.digest if self.selection else None,
            "blueprint_digest": self.blueprint.digest if self.blueprint else None,
            "result_digest": self.result_digest,
            "generated_manifest_digest": self.generated_manifest_digest,
            "generated_file_digests": [
                {"path": path, "digest": digest}
                for path, digest in self.generated_file_digests
            ],
            "import_digest": self.import_digest,
            "import_status": self.import_status,
            "validation_digest": self.validation_digest,
            "validation_status": self.validation_status,
            "promotion_digest": self.promotion_digest,
            "promotion_status": self.promotion_status,
        }

    def to_snapshot(self) -> dict[str, object]:
        payload = self.to_payload()
        payload["inventory"] = (
            {
                "adapter_id": self.inventory.adapter_id,
                "adapter_version": self.inventory.adapter_version,
                "artifacts": [
                    {
                        "name": item.name,
                        "digest": item.digest,
                        "size_bytes": item.size_bytes,
                        "media_type": item.media_type,
                    }
                    for item in self.inventory.artifacts
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
                    for item in self.inventory.units
                ],
            }
            if self.inventory
            else None
        )
        payload["selection"] = (
            {
                "selected": list(self.selection.selected),
                "auto_included": list(self.selection.auto_included),
                "reasons": [list(item) for item in self.selection.reasons],
            }
            if self.selection
            else None
        )
        payload["blueprint"] = (
            {
                "source_digest": self.blueprint.source_digest,
                "rules": [
                    {
                        "rule_id": item.rule_id,
                        "classification": item.classification,
                        "evidence": item.evidence,
                        "effect": item.effect,
                    }
                    for item in self.blueprint.rules
                ],
            }
            if self.blueprint
            else None
        )
        return payload

    @classmethod
    def from_snapshot(cls, payload: dict[str, object]) -> MigrationSession:
        inventory_payload = cast(dict[str, object] | None, payload.get("inventory"))
        inventory = None
        if inventory_payload is not None:
            inventory = SourceInventory(
                str(inventory_payload["adapter_id"]),
                str(inventory_payload["adapter_version"]),
                tuple(
                    SourceArtifact(
                        str(item["name"]),
                        str(item["digest"]),
                        cast(int, item["size_bytes"]),
                        str(item.get("media_type", "application/octet-stream")),
                    )
                    for item in cast(list[dict[str, object]], inventory_payload["artifacts"])
                ),
                tuple(
                    MigrationUnit(
                        str(item["key"]),
                        str(item["kind"]),
                        str(item["name"]),
                        cast(ObjectState, item["state"]),
                        tuple(cast(list[str], item.get("dependencies", []))),
                        tuple(cast(list[str], item.get("source_refs", []))),
                        tuple(cast(list[str], item.get("notes", []))),
                    )
                    for item in cast(list[dict[str, object]], inventory_payload["units"])
                ),
            )
        selection_payload = cast(dict[str, object] | None, payload.get("selection"))
        selection = (
            None
            if selection_payload is None
            else ScopeSelection(
                tuple(cast(list[str], selection_payload["selected"])),
                tuple(cast(list[str], selection_payload.get("auto_included", []))),
                tuple(
                    (str(item[0]), str(item[1]))
                    for item in cast(list[list[str]], selection_payload.get("reasons", []))
                    if len(item) == 2
                ),
            )
        )
        blueprint_payload = cast(dict[str, object] | None, payload.get("blueprint"))
        blueprint = (
            None
            if blueprint_payload is None
            else BlueprintContract(
                str(blueprint_payload["source_digest"]),
                tuple(
                    BlueprintRule(
                        str(item["rule_id"]),
                        cast(RuleClass, item["classification"]),
                        str(item["evidence"]),
                        str(item["effect"]),
                    )
                    for item in cast(list[dict[str, object]], blueprint_payload["rules"])
                ),
            )
        )
        return cls(
            str(payload["id"]),
            str(payload["workspace_id"]),
            str(payload["project_id"]),
            cast(SessionState, payload["state"]),
            inventory,
            selection,
            blueprint,
            cast(str | None, payload.get("result_digest")),
            cast(str | None, payload.get("generated_manifest_digest")),
            tuple(
                (str(item["path"]), str(item["digest"]))
                for item in cast(list[dict[str, object]], payload.get("generated_file_digests", []))
            ),
            cast(str | None, payload.get("import_digest")),
            cast(str | None, payload.get("import_status")),
            cast(str | None, payload.get("validation_digest")),
            cast(str | None, payload.get("validation_status")),
            cast(str | None, payload.get("promotion_digest")),
            cast(str | None, payload.get("promotion_status")),
        )


class MigrationSessionService:
    """Small deterministic service; storage adapters can persist its snapshots."""

    def __init__(self, store: object | None = None) -> None:
        self._sessions: dict[str, MigrationSession] = {}
        self._store = store

    def _save(self, session: MigrationSession) -> None:
        if self._store is not None:
            save = getattr(self._store, "save", None)
            if not callable(save):
                raise TypeError("migration session store must provide save(session)")
            save(session)

    def create(self, workspace_id: str, project_id: str) -> MigrationSession:
        if not workspace_id or not project_id:
            raise ValueError("workspace_id and project_id are required")
        seed = f"{workspace_id}\0{project_id}\0{len(self._sessions)}".encode()
        session = MigrationSession(
            "migration-" + hashlib.sha256(seed).hexdigest()[:24], workspace_id, project_id
        )
        self._sessions[session.id] = session
        self._save(session)
        return session

    def get(self, session_id: str) -> MigrationSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            load = getattr(self._store, "load", None)
            if callable(load):
                try:
                    session = load(session_id)
                except KeyError:
                    pass
                else:
                    self._sessions[session_id] = session
                    return cast(MigrationSession, session)
            raise KeyError(f"migration session not found: {session_id}") from exc

    def store_list(self, workspace_id: str, project_id: str) -> tuple[dict[str, object], ...]:
        if self._store is not None:
            list_method = getattr(self._store, "list", None)
            if callable(list_method):
                return tuple(list_method(workspace_id=workspace_id, project_id=project_id))
        return tuple(
            session.to_payload()
            for session in self._sessions.values()
            if session.workspace_id == workspace_id and session.project_id == project_id
        )

    def discover(self, session_id: str, inventory: SourceInventory) -> MigrationSession:
        session = self.get(session_id)
        self._require(session, {"draft", "artifacts_ready", "discovering"})
        existing = session.inventory.artifacts if session.inventory is not None else ()
        known = {item.name for item in inventory.artifacts}
        merged_inventory = SourceInventory(
            inventory.adapter_id,
            inventory.adapter_version,
            (*existing, *(item for item in inventory.artifacts if item.name not in known)),
            inventory.units,
        )
        self._check_artifact_budget(merged_inventory.artifacts)
        updated = replace(session, state="scope_ready", inventory=merged_inventory)
        self._sessions[session_id] = updated
        self._save(updated)
        return updated

    def add_artifact(self, session_id: str, artifact: SourceArtifact) -> MigrationSession:
        session = self.get(session_id)
        self._require(session, {"draft", "artifacts_ready", "discovering", "scope_ready"})
        inventory = session.inventory
        if inventory is None:
            inventory = SourceInventory("iics", "unknown", (), ())
        if any(item.name == artifact.name for item in inventory.artifacts):
            raise ValueError(f"artifact already exists: {artifact.name}")
        self._check_artifact_budget((*inventory.artifacts, artifact))
        updated_inventory = SourceInventory(
            inventory.adapter_id,
            inventory.adapter_version,
            (*inventory.artifacts, artifact),
            inventory.units,
        )
        updated = replace(session, inventory=updated_inventory, state="artifacts_ready")
        self._sessions[session_id] = updated
        self._save(updated)
        return updated

    @staticmethod
    def _check_artifact_budget(artifacts: tuple[SourceArtifact, ...]) -> None:
        if len(artifacts) > MAX_SESSION_ARTIFACTS:
            raise ValueError(f"session supports at most {MAX_SESSION_ARTIFACTS} artifacts")
        total_bytes = sum(item.size_bytes for item in artifacts)
        if total_bytes > MAX_SESSION_ARTIFACT_BYTES:
            raise ValueError(f"session artifacts exceed {MAX_SESSION_ARTIFACT_BYTES} total bytes")

    def set_scope(self, session_id: str, requested: tuple[str, ...]) -> MigrationSession:
        session = self.get(session_id)
        self._require(session, {"scope_ready"})
        if session.inventory is None:
            raise ValueError("session has no inventory")
        updated = replace(session, selection=select_scope(session.inventory, requested))
        self._sessions[session_id] = updated
        self._save(updated)
        return updated

    def set_blueprint(self, session_id: str, blueprint: BlueprintContract) -> MigrationSession:
        session = self.get(session_id)
        self._require(session, {"scope_ready"})
        updated = replace(session, blueprint=blueprint)
        self._sessions[session_id] = updated
        self._save(updated)
        return updated

    def begin_conversion(self, session_id: str) -> MigrationSession:
        session = self.get(session_id)
        self._require(session, {"scope_ready"})
        if session.inventory is None or session.selection is None:
            raise ValueError("conversion requires inventory and frozen scope")
        updated = replace(session, state="converting")
        self._sessions[session_id] = updated
        self._save(updated)
        return updated

    def generate(self, session_id: str) -> GeneratedProject:
        session = self.get(session_id)
        self._require(session, {"scope_ready", "converting", "qualifying", "completed"})
        if session.inventory is None or session.selection is None:
            raise ValueError("generation requires inventory and frozen scope")
        project = generate_project(
            inventory=session.inventory,
            selection=session.selection,
            blueprint=session.blueprint,
        )
        updated = replace(session, state="converting", result_digest=project.project_digest)
        updated = replace(
            updated,
            generated_manifest_digest=hashlib.sha256(project.manifest.encode()).hexdigest(),
            generated_file_digests=tuple(
                (item.path, hashlib.sha256(item.content.encode()).hexdigest())
                for item in project.files
            ),
        )
        self._sessions[session_id] = updated
        self._save(updated)
        return project

    def record_import(
        self, session_id: str, project: GeneratedProject, *, target: str
    ) -> MigrationSession:
        """Persist deterministic import evidence without claiming target-side execution."""
        session = self.get(session_id)
        self._require(session, {"converting", "qualifying", "completed"})
        if not target or target != target.strip():
            raise ValueError("import target is required")
        expected = generate_project(
            inventory=session.inventory, selection=session.selection, blueprint=session.blueprint
        ) if session.inventory is not None and session.selection is not None else None
        if expected is None or expected.project_digest != project.project_digest:
            raise ValueError("generated project does not match the frozen session scope")
        evidence = json.dumps(
            {
                "project_digest": project.project_digest,
                "target": target,
                "files": [item.path for item in project.files],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        updated = replace(
            session,
            import_digest=hashlib.sha256(evidence).hexdigest(),
            import_status="importable",
        )
        self._sessions[session_id] = updated
        self._save(updated)
        return updated

    def qualify_generated(self, session_id: str) -> GeneratedQualification:
        session = self.get(session_id)
        self._require(session, {"converting", "qualifying"})
        if session.inventory is None or session.selection is None:
            raise ValueError("qualification requires generated scope")
        project = self.generate(session_id)
        session = self.get(session_id)
        qualification = qualify_generated_project(project)
        updated = replace(session, state="qualifying")
        self._sessions[session_id] = updated
        self._save(updated)
        return qualification

    def validate(
        self,
        session_id: str,
        expected: list[dict[str, object]],
        actual: list[dict[str, object]],
        *,
        asset_id: str | None = None,
        level: ReportLevel = "simple",
        modes: tuple[CheckMode, ...] = ("schema", "counts", "multiset"),
        key_columns: tuple[str, ...] = (),
        tolerances: dict[str, float] | None = None,
    ) -> ValidationReport:
        session = self.get(session_id)
        self._require(session, {"draft", "scope_ready", "converting", "qualifying", "completed"})
        report = validate_results(
            expected,
            actual,
            asset_id=asset_id or session_id,
            level=level,
            modes=modes,
            key_columns=key_columns,
            tolerances=tolerances,
        )
        updated = replace(
            session,
            validation_digest=report.digest,
            validation_status=report.status,
        )
        self._sessions[session_id] = updated
        self._save(updated)
        return report

    def record_promotion(
        self, session_id: str, evidence: dict[str, object], *, promoted: bool
    ) -> MigrationSession:
        session = self.get(session_id)
        self._require(session, {"draft", "scope_ready", "converting", "qualifying", "completed"})
        encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
        updated = replace(
            session,
            promotion_digest=hashlib.sha256(encoded).hexdigest(),
            promotion_status="promoted" if promoted else "rejected",
        )
        self._sessions[session_id] = updated
        self._save(updated)
        return updated

    def complete(self, session_id: str, result_digest: str) -> MigrationSession:
        session = self.get(session_id)
        self._require(session, {"converting", "qualifying"})
        if not result_digest or result_digest != result_digest.strip():
            raise ValueError("result_digest is required")
        updated = replace(session, state="completed", result_digest=result_digest)
        self._sessions[session_id] = updated
        self._save(updated)
        return updated

    @staticmethod
    def _require(session: MigrationSession, states: set[SessionState]) -> None:
        if session.state not in states:
            raise ValueError(f"session state {session.state} does not allow this operation")


__all__ = ("MigrationSession", "MigrationSessionService")
