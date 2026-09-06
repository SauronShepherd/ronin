from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from studio_core import (
    CapabilityRequirement,
    ExecutionProfile,
    Project,
    ProjectId,
    ProjectManifest,
    RepositoryBinding,
    RuntimeCatalog,
    RuntimeProfile,
    RuntimeProfileRef,
)
from studio_kernel import RepositoryRevision
from studio_notebook import CellId, NotebookCell
from studio_orchestrator import AttemptId, Job, JobId, JobState, RunId
from studio_vcs import GitRevision
from studio_worker import (
    LOCAL_DOCKER_PROFILE,
    LoadedProject,
    PythonCellAdapter,
    WorkerPaths,
    WorkerPreparationError,
    build_request,
    execution_identities,
    load_project,
    resolve_runtime_snapshot,
    runtime_snapshot_digest,
)

NOW = "2026-09-06T17:00:00.000000Z"


def _job(
    *,
    project_id: str = "examples/demo",
    target: str = "notebooks/etl.ronin.json",
    parameters_json: str = '{"limit":10,"mode":"demo"}',
) -> Job:
    return Job(
        id=JobId("job-worker-preparation"),
        project_id=project_id,
        idempotency_key="worker-preparation-key",
        request_digest="a" * 64,
        state=JobState.QUEUED,
        created_at=NOW,
        updated_at=NOW,
        target=target,
        parameters_json=parameters_json,
    )


def _load_demo(monkeypatch: pytest.MonkeyPatch) -> LoadedProject:
    monkeypatch.setattr(
        "studio_worker.preparation.capture_revision",
        lambda _path: GitRevision("b" * 40, "c" * 64),
    )
    return load_project(WorkerPaths(Path.cwd(), Path(".ronin-data")), _job())


def test_worker_paths_reject_project_escape(tmp_path: Path) -> None:
    paths = WorkerPaths(tmp_path, tmp_path / "data")
    assert paths.project_dir("project") == (tmp_path / "project").resolve()
    with pytest.raises(WorkerPreparationError, match="escapes"):
        paths.project_dir("../outside")


def test_load_project_uses_real_fixture_and_captured_dirty_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = _load_demo(monkeypatch)
    assert loaded.manifest.project.id == ProjectId("demo")
    assert len(loaded.document.notebook.cells) == 6
    assert loaded.revision == RepositoryRevision("b" * 40, "c" * 64)
    assert loaded.project_dir == (Path.cwd() / "examples" / "demo").resolve()


def test_load_project_missing_manifest_names_absolute_path(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(WorkerPreparationError) as exc_info:
        load_project(WorkerPaths(tmp_path, tmp_path / "data"), _job(project_id="project"))
    expected = str((project / ".ronin" / "project.json").resolve())
    assert expected in str(exc_info.value)


def test_load_project_rejects_empty_and_escaping_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = _load_demo(monkeypatch)
    paths = WorkerPaths(Path.cwd(), Path(".ronin-data"))
    with pytest.raises(WorkerPreparationError, match="target is required"):
        load_project(paths, _job(target=""))
    assert loaded.manifest.project.id == ProjectId("demo")
    with pytest.raises(WorkerPreparationError, match="notebook target path escapes"):
        load_project(paths, _job(target="../../pyproject.toml"))


def test_local_runtime_resolves_demo_and_builds_five_python_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = _load_demo(monkeypatch)
    runtime = resolve_runtime_snapshot(loaded.manifest, RuntimeCatalog((LOCAL_DOCKER_PROFILE,)))
    request = build_request(loaded, runtime, AttemptId("attempt-1"))
    assert runtime.resolved_profile.ref == RuntimeProfileRef("docker", "python-3.11-slim")
    assert len(runtime_snapshot_digest(runtime)) == 64
    assert len(request.cells) == 5
    assert all(cell.language == "python" for cell in request.cells)


def test_runtime_resolution_fails_closed_without_compatible_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = _load_demo(monkeypatch)
    incompatible = RuntimeProfile(RuntimeProfileRef("docker", "other"), ())
    with pytest.raises(WorkerPreparationError, match="not resolvable"):
        resolve_runtime_snapshot(loaded.manifest, RuntimeCatalog((incompatible,)))


def test_python_adapter_rejects_non_python_cells() -> None:
    adapter = PythonCellAdapter()
    with pytest.raises(WorkerPreparationError, match="Python code"):
        adapter.prepare(NotebookCell(CellId("note"), "markdown", "text"))


def test_identity_chain_invalidates_all_downstream_dependents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = _load_demo(monkeypatch)
    runtime = resolve_runtime_snapshot(loaded.manifest, RuntimeCatalog((LOCAL_DOCKER_PROFILE,)))
    request = build_request(loaded, runtime, AttemptId("attempt-1"))
    original = execution_identities(request, run_id=RunId("run-1"), loaded=loaded, job=_job())

    changed_first = replace(
        request.cells[0],
        authored_source=request.cells[0].authored_source + "\nprint('changed')",
    )
    changed_request = replace(request, cells=(changed_first, *request.cells[1:]))
    changed = execution_identities(
        changed_request,
        run_id=RunId("run-1"),
        loaded=loaded,
        job=_job(),
    )

    assert original[0].digest != changed[0].digest
    assert original[1].digest == changed[1].digest
    assert tuple(item.digest for item in original[2:]) != tuple(item.digest for item in changed[2:])
    assert changed[2].upstream_result_digests[0] == changed[0].digest
    assert changed[3].upstream_result_digests == (changed[2].digest,)
    assert changed[4].upstream_result_digests == (changed[3].digest,)


def test_identity_changes_for_dirty_revision_and_not_json_key_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = _load_demo(monkeypatch)
    runtime = resolve_runtime_snapshot(loaded.manifest, RuntimeCatalog((LOCAL_DOCKER_PROFILE,)))
    request = build_request(loaded, runtime, AttemptId("attempt-1"))
    first = execution_identities(
        request,
        run_id=RunId("run-1"),
        loaded=loaded,
        job=_job(parameters_json='{"a":1,"b":2}'),
    )[0]
    reordered = execution_identities(
        request,
        run_id=RunId("run-1"),
        loaded=loaded,
        job=_job(parameters_json='{"b":2,"a":1}'),
    )[0]
    dirty_changed = execution_identities(
        request,
        run_id=RunId("run-1"),
        loaded=replace(loaded, revision=RepositoryRevision("b" * 40, "d" * 64)),
        job=_job(parameters_json='{"a":1,"b":2}'),
    )[0]
    assert first.parameter_digest == reordered.parameter_digest
    assert first.digest == reordered.digest
    assert first.repository_digest != dirty_changed.repository_digest
    assert first.digest != dirty_changed.digest


def test_execution_identities_reject_missing_dependency_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = _load_demo(monkeypatch)
    runtime = resolve_runtime_snapshot(loaded.manifest, RuntimeCatalog((LOCAL_DOCKER_PROFILE,)))
    request = build_request(loaded, runtime, AttemptId("attempt-1"))
    broken = replace(request.cells[0], dependencies=(CellId("missing"),))
    with pytest.raises(WorkerPreparationError, match="dependency identity missing"):
        execution_identities(
            replace(request, cells=(broken, *request.cells[1:])),
            run_id=RunId("run-1"),
            loaded=loaded,
            job=_job(),
        )


def test_runtime_digest_supports_requirement_only_resolution() -> None:
    manifest = ProjectManifest(
        Project(
            ProjectId("portable"),
            "Portable",
            (RepositoryBinding("main", "https://example.invalid/repo", role="primary"),),
            ExecutionProfile(requirements=(CapabilityRequirement("python", ">=3.11"),)),
        ),
    )
    runtime = resolve_runtime_snapshot(manifest, RuntimeCatalog((LOCAL_DOCKER_PROFILE,)))
    assert runtime.requested_profile is None
    assert len(runtime_snapshot_digest(runtime)) == 64
