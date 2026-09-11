"""Prepare durable worker claims without coupling canonical domain code to Docker or SQLite."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from studio_core import (
    ProjectManifest,
    ResolvedRuntimeSnapshot,
    RuntimeCapability,
    RuntimeCatalog,
    RuntimeProfile,
    RuntimeProfileRef,
    resolve_runtime,
    snapshot_runtime_resolution,
)
from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json
from studio_kernel import (
    CellExecutionRequest,
    ExecutionAttemptId,
    ExecutionReproducibilitySnapshot,
    KernelDirective,
    NotebookExecutionRequest,
    PreparedCell,
    RepositoryRevision,
    prepare_notebook_execution,
)
from studio_notebook import NotebookCell, NotebookDocument
from studio_orchestrator import AttemptId, CellExecutionIdentity, Job, RunId
from studio_vcs import capture_revision


class WorkerPreparationError(RuntimeError):
    """Raised when one durable claim cannot be prepared safely for execution."""


@dataclass(frozen=True, slots=True)
class WorkerPaths:
    workspace_root: Path
    data_dir: Path

    def project_dir(self, project_id: str) -> Path:
        return _contained_path(self.workspace_root, project_id, "project")


@dataclass(frozen=True, slots=True)
class LoadedProject:
    manifest: ProjectManifest
    document: NotebookDocument
    revision: RepositoryRevision
    project_dir: Path


@dataclass(frozen=True, slots=True)
class PythonCellAdapter:
    """Minimal Python preparation adapter for the local v0.1 execution path."""

    @property
    def adapter_id(self) -> str:
        return "python"

    def prepare(self, cell: NotebookCell) -> PreparedCell:
        if cell.kind != "code" or cell.language != "python":
            raise WorkerPreparationError("local Python adapter only accepts Python code cells")
        return PreparedCell(
            cell.id,
            cell.source,
            KernelDirective(adapter_id=self.adapter_id, kind="exec"),
        )


LOCAL_DOCKER_PROFILE = RuntimeProfile(
    RuntimeProfileRef("docker", "python-3.11-slim"),
    (
        RuntimeCapability("container", "1"),
        RuntimeCapability("python", "3.11"),
    ),
)


def _contained_path(root: Path, relative: str, name: str) -> Path:
    base = root.resolve()
    candidate = (base / relative).resolve()
    if not candidate.is_relative_to(base):
        raise WorkerPreparationError(f"{name} path escapes the workspace root")
    return candidate


def _read_text(path: Path, name: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorkerPreparationError(f"cannot read {name}: {path}") from exc


def load_project(paths: WorkerPaths, job: Job) -> LoadedProject:
    """Load portable project/notebook intent and capture the exact local Git revision."""

    project_dir = paths.project_dir(job.project_id)
    manifest_path = project_dir / ".ronin" / "project.json"
    manifest = ProjectManifest.from_json(_read_text(manifest_path, "project manifest"))
    if not job.target:
        raise WorkerPreparationError("job target is required for worker execution")
    target_path = _contained_path(project_dir, job.target, "notebook target")
    document = NotebookDocument.from_json(_read_text(target_path, "notebook target"))
    revision = capture_revision(project_dir)
    return LoadedProject(
        manifest=manifest,
        document=document,
        revision=RepositoryRevision(revision.commit, revision.dirty_patch_sha256),
        project_dir=project_dir,
    )


def resolve_runtime_snapshot(
    manifest: ProjectManifest,
    catalog: RuntimeCatalog,
) -> ResolvedRuntimeSnapshot:
    """Resolve portable execution intent and freeze the selected runtime evidence."""

    resolution = resolve_runtime(manifest.project.execution, catalog)
    snapshot = snapshot_runtime_resolution(manifest.project.execution, resolution)
    if snapshot is None:
        raise WorkerPreparationError(f"runtime not resolvable: {resolution.status}")
    return snapshot


def build_request(
    loaded: LoadedProject,
    runtime: ResolvedRuntimeSnapshot,
    attempt_id: AttemptId,
) -> NotebookExecutionRequest:
    """Build the immutable kernel request consumed by a concrete executor."""

    return prepare_notebook_execution(
        loaded.document,
        runtime,
        loaded.revision,
        PythonCellAdapter(),
        attempt_id=ExecutionAttemptId(str(attempt_id)),
        reproducibility=ExecutionReproducibilitySnapshot(),
    )


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(encode_canonical_json(value)).hexdigest()


def _profile_ref(ref: RuntimeProfileRef | None) -> object:
    if ref is None:
        return None
    return {"adapter_id": ref.adapter_id, "profile_id": ref.profile_id}


def runtime_snapshot_digest(runtime: ResolvedRuntimeSnapshot) -> str:
    """Hash the complete provider-neutral runtime snapshot without relying on repr()."""

    profile = runtime.resolved_profile
    payload = {
        "requested_profile": _profile_ref(runtime.requested_profile),
        "resolved_profile": {
            "ref": _profile_ref(profile.ref),
            "available": profile.available,
            "capabilities": [
                {"name": capability.name, "value": capability.value}
                for capability in profile.capabilities
            ],
        },
        "resolution_policy": runtime.resolution_policy,
        "exact_profile_selected": runtime.exact_profile_selected,
        "checks": [
            {
                "requirement": {
                    "name": check.requirement.name,
                    "constraint": check.requirement.constraint,
                    "level": check.requirement.level,
                },
                "advertised_value": check.advertised_value,
                "satisfied": check.satisfied,
                "reason": check.reason,
            }
            for check in runtime.checks
        ],
        "preferred_matches": runtime.preferred_matches,
        "version": 1,
    }
    return _canonical_digest(payload)


def _repository_digest(revision: RepositoryRevision) -> str:
    return _canonical_digest(
        {
            "commit": revision.commit,
            "dirty_patch_sha256": revision.dirty_patch_sha256,
            "version": 1,
        }
    )


def _parameter_digest(parameters_json: str) -> str:
    try:
        parameters = decode_canonical_json(parameters_json)
    except (TypeError, ValueError) as exc:
        raise WorkerPreparationError("job parameters_json must be canonical-boundary JSON") from exc
    return _canonical_digest(parameters)


def identity_for(
    cell: CellExecutionRequest,
    *,
    run_id: RunId,
    loaded: LoadedProject,
    runtime: ResolvedRuntimeSnapshot,
    job: Job,
    upstream: tuple[str, ...],
) -> CellExecutionIdentity:
    """Bind one executable cell to all inputs required for safe record-level reuse."""

    return CellExecutionIdentity(
        run_id=run_id,
        cell_id=str(cell.cell_id),
        source_digest=hashlib.sha256(cell.authored_source.encode("utf-8")).hexdigest(),
        repository_digest=_repository_digest(loaded.revision),
        runtime_digest=runtime_snapshot_digest(runtime),
        parameter_digest=_parameter_digest(job.parameters_json),
        upstream_result_digests=upstream,
    )


def execution_identities(
    request: NotebookExecutionRequest,
    *,
    run_id: RunId,
    loaded: LoadedProject,
    job: Job,
) -> tuple[CellExecutionIdentity, ...]:
    """Build identities in execution order, chaining direct dependency identity digests."""

    digests: dict[str, str] = {}
    identities: list[CellExecutionIdentity] = []
    for cell in request.cells:
        try:
            upstream = tuple(digests[str(dependency)] for dependency in cell.dependencies)
        except KeyError as exc:
            raise WorkerPreparationError(
                "dependency identity missing before dependent cell"
            ) from exc
        identity = identity_for(
            cell,
            run_id=run_id,
            loaded=loaded,
            runtime=request.runtime,
            job=job,
            upstream=upstream,
        )
        digests[str(cell.cell_id)] = identity.digest
        identities.append(identity)
    return tuple(identities)
