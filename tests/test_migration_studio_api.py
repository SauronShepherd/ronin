import base64
import io
import zipfile

from studio_migration import (
    MigrationAPIRouter,
    MigrationSessionService,
    MigrationUnit,
    SourceInventory,
)


def test_migration_api_creates_and_lists_project_scoped_sessions() -> None:
    router = MigrationAPIRouter(MigrationSessionService())
    path = "/v1/workspaces/ws-1/projects/project-1/migration/sessions"
    created = router.dispatch("POST", path, {}, authorized=True)
    assert created.status == 201
    listed = router.dispatch("GET", path, authorized=True)
    assert listed.status == 200
    assert len(listed.payload["items"]) == 1


def test_migration_api_lists_adapters_and_ingests_source_artifact() -> None:
    router = MigrationAPIRouter(MigrationSessionService())
    base = "/v1/workspaces/ws-1/projects/project-1/migration/sessions"
    adapters = router.dispatch(
        "GET", "/v1/workspaces/ws-1/projects/project-1/migration/adapters", authorized=True
    )
    assert adapters.status == 200
    assert adapters.payload["items"][0]["adapter_id"] == "iics"
    session_id = router.dispatch("POST", base, {}, authorized=True).payload["id"]
    artifact = router.dispatch(
        "PUT",
        f"{base}/{session_id}/source-artifacts/export.zip",
        {"content_base64": base64.b64encode(b"fixture").decode(), "media_type": "application/zip"},
        authorized=True,
    )
    assert artifact.status == 200
    assert artifact.payload["state"] == "artifacts_ready"
    assert artifact.payload["inventory_digest"]
    binary = router.dispatch(
        "PUT",
        f"{base}/{session_id}/source-artifacts/binary.zip",
        b"binary-fixture",
        authorized=True,
    )
    assert binary.status == 200
    unsafe = router.dispatch(
        "PUT",
        f"{base}/{session_id}/source-artifacts/bad name",
        {"content_base64": base64.b64encode(b"fixture").decode()},
        authorized=True,
    )
    assert unsafe.status == 400


def test_migration_api_discovers_named_vendor_profiles_into_canonical_inventory() -> None:
    router = MigrationAPIRouter(MigrationSessionService())
    base = "/v1/workspaces/ws-1/projects/project-1/migration/sessions"
    session_id = router.dispatch("POST", base, {}, authorized=True).payload["id"]
    discovered = router.dispatch(
        "POST",
        f"{base}/{session_id}/discover",
        {
            "profile": "databricks",
            "source_version": "15.4",
            "document_base64": base64.b64encode(
                b'{"jobs":[{"id":"job-1"}],"pipelines":[{"id":"pipe-1"}]}'
            ).decode(),
        },
        authorized=True,
    )
    assert discovered.status == 200
    inventory = router.dispatch(
        "GET", f"{base}/{session_id}/inventory", authorized=True
    )
    assert inventory.status == 200
    assert inventory.payload["adapter_id"] == "databricks"
    assert {item["key"] for item in inventory.payload["units"]} == {
        "job:job-1",
        "pipeline:pipe-1",
    }


def test_migration_api_converts_named_vendor_profile_to_workflow_and_loss_report() -> None:
    router = MigrationAPIRouter(MigrationSessionService())
    base = "/v1/workspaces/ws-1/projects/project-1/migration/sessions"
    session_id = router.dispatch("POST", base, {}, authorized=True).payload["id"]
    converted = router.dispatch(
        "POST",
        f"{base}/{session_id}/convert",
        {
            "profile": "fabric",
            "source_version": "2026",
            "document_base64": base64.b64encode(
                b'{"id":"fabric-project","items":[{"id":"nb-1","type":"notebook","path":"/jobs/nb"}]}'
            ).decode(),
        },
        authorized=True,
    )
    assert converted.status == 200
    assert converted.payload["profile"] == "fabric"
    assert converted.payload["workflow"]["id"] == "fabric-project-fabric-project"
    assert converted.payload["report"]["objects"][0]["status"] == "translated"
    assert len(converted.payload["report_digest"]) == 64


def test_migration_api_records_canonical_import_evidence() -> None:
    service = MigrationSessionService()
    router = MigrationAPIRouter(service)
    base = "/v1/workspaces/ws-1/projects/project-1/migration/sessions"
    session_id = router.dispatch("POST", base, {}, authorized=True).payload["id"]
    service.discover(
        session_id,
        SourceInventory(
            "databricks", "15.4", (), (MigrationUnit("notebook:nb-1", "notebook", "nb-1", "ready"),)
        ),
    )
    service.set_scope(session_id, ("notebook:nb-1",))
    imported = router.dispatch(
        "POST", f"{base}/{session_id}/import", {"target": "project-catalog"}, authorized=True
    )
    assert imported.status == 200
    assert imported.payload["status"] == "importable"
    assert len(imported.payload["import_digest"]) == 64
    assert imported.payload["session"]["import_status"] == "importable"


def test_migration_api_hides_other_project_session_and_requires_auth() -> None:
    router = MigrationAPIRouter(MigrationSessionService())
    path = "/v1/workspaces/ws-1/projects/project-1/migration/sessions"
    created = router.dispatch("POST", path, {}, authorized=True)
    session_id = created.payload["id"]
    hidden = router.dispatch(
        "GET",
        f"/v1/workspaces/ws-2/projects/project-2/migration/sessions/{session_id}",
        authorized=True,
    )
    assert hidden.status == 404
    assert router.dispatch("GET", path, authorized=False).status == 401


def test_migration_api_discovers_iics_then_freezes_scope_and_blueprint() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("pkg/DTEMPLATE.json", '{"assetFrsGuid":"map-1"}')
        archive.writestr("pkg/MTT.json", '{"mappingId":"map-1","id":"proc-1"}')
    router = MigrationAPIRouter(MigrationSessionService())
    base = "/v1/workspaces/ws/projects/p/migration/sessions"
    session = router.dispatch("POST", base, {}, authorized=True).payload
    session_id = session["id"]
    discovered = router.dispatch(
        "POST",
        f"{base}/{session_id}/discover",
        {
            "archives": [
                {
                    "name": "export.zip",
                    "content_base64": base64.b64encode(stream.getvalue()).decode(),
                }
            ]
        },
        authorized=True,
    )
    assert discovered.status == 200
    scoped = router.dispatch(
        "PUT", f"{base}/{session_id}/scope", {"selected": ["iics:process:proc-1"]}, authorized=True
    )
    assert scoped.status == 200
    blueprint = router.dispatch(
        "PUT", f"{base}/{session_id}/blueprint", {"conventions": {"io": "delta"}}, authorized=True
    )
    assert blueprint.status == 200
    assert blueprint.payload["blueprint_digest"] is not None
    uploaded_blueprint = router.dispatch(
        "PUT",
        f"{base}/{session_id}/blueprint/reference.json",
        b'{"conventions":{"io":"delta"}}',
        authorized=True,
    )
    assert uploaded_blueprint.status == 200
    assert uploaded_blueprint.payload["blueprint_digest"] == blueprint.payload["blueprint_digest"]
    inventory = router.dispatch("GET", f"{base}/{session_id}/inventory", authorized=True)
    assert inventory.status == 200
    assert inventory.payload["digest"] == discovered.payload["inventory_digest"]
    contract = router.dispatch("GET", f"{base}/{session_id}/blueprint-contract", authorized=True)
    assert contract.status == 200
    assert contract.payload["digest"] == blueprint.payload["blueprint_digest"]
    result = router.dispatch("GET", f"{base}/{session_id}/result", authorized=True)
    assert result.status == 200
    assert result.payload["state"] == "scope_ready"


def test_migration_api_generates_and_qualifies_persisted_session() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("mapping.dtemplate.json", '{"mappingId":"map-1"}')
        archive.writestr("process.mtt.json", '{"id":"proc-1","mappingId":"map-1"}')
    router = MigrationAPIRouter(MigrationSessionService())
    base = "/v1/workspaces/ws/projects/p/migration/sessions"
    session_id = router.dispatch("POST", base, {}, authorized=True).payload["id"]
    router.dispatch(
        "POST",
        f"{base}/{session_id}/discover",
        {
            "archives": [
                {
                    "name": "export.zip",
                    "content_base64": base64.b64encode(stream.getvalue()).decode(),
                }
            ]
        },
        authorized=True,
    )
    router.dispatch(
        "PUT", f"{base}/{session_id}/scope", {"selected": ["iics:process:proc-1"]}, authorized=True
    )
    generated = router.dispatch("POST", f"{base}/{session_id}/convert", {}, authorized=True)
    assert generated.status == 200
    assert generated.payload["project_digest"]
    assert generated.payload["files"]
    exported = router.dispatch("GET", f"{base}/{session_id}/export", authorized=True)
    assert exported.status == 200
    assert exported.payload["filename"] == "ronin_migration.py"
    assert "--source" in exported.payload["content"]
    assert exported.payload["project_digest"] == generated.payload["project_digest"]
    immutable = router.dispatch(
        "PUT",
        f"{base}/{session_id}/source-artifacts/late.zip",
        b"late-artifact",
        authorized=True,
    )
    assert immutable.status == 400
    qualified = router.dispatch("POST", f"{base}/{session_id}/qualify", {}, authorized=True)
    assert qualified.status == 200
    assert qualified.payload["status"] == "passed"
    qualification = router.dispatch("GET", f"{base}/{session_id}/qualification", authorized=True)
    assert qualification.status == 200
    findings = router.dispatch("GET", f"{base}/{session_id}/findings", authorized=True)
    assert findings.status == 200
    assert findings.payload["status"] == "passed"


def test_migration_api_returns_simple_and_full_result_reports() -> None:
    router = MigrationAPIRouter(MigrationSessionService())
    base = "/v1/workspaces/ws/projects/p/migration/sessions"
    session_id = router.dispatch("POST", base, {}, authorized=True).payload["id"]
    response = router.dispatch(
        "POST",
        f"{base}/{session_id}/validate",
        {
            "asset_id": "orders",
            "expected": [{"id": "a", "amount": 10.0}],
            "actual": [{"id": "a", "amount": 10.005}],
            "level": "full",
            "modes": ["keyed"],
            "key_columns": ["id"],
            "tolerances": {"amount": 0.01},
        },
        authorized=True,
    )
    assert response.status == 200
    assert response.payload["status"] == "pass"
    assert response.payload["level"] == "full"
    assert response.payload["session"]["validation_digest"] == response.payload["digest"]
    assert response.payload["session"]["validation_status"] == "pass"


def test_migration_api_renders_downloadable_report_and_rejects_unknown_format() -> None:
    router = MigrationAPIRouter(MigrationSessionService())
    base = "/v1/workspaces/ws/projects/p/migration/sessions"
    session_id = router.dispatch("POST", base, {}, authorized=True).payload["id"]
    path = f"{base}/{session_id}/validate"
    response = router.dispatch(
        "POST",
        path,
        {
            "expected": [{"id": "a"}],
            "actual": [{"id": "a"}],
            "format": "html",
        },
        authorized=True,
    )
    assert response.status == 200
    assert response.payload["format"] == "html"
    assert response.payload["content"].startswith("<!doctype html>")
    invalid = router.dispatch(
        "POST", path, {"expected": [], "actual": [], "format": "pdf"}, authorized=True
    )
    assert invalid.status == 400


def test_migration_api_rejects_malformed_or_unbounded_validation_input() -> None:
    router = MigrationAPIRouter(MigrationSessionService())
    base = "/v1/workspaces/ws/projects/p/migration/sessions"
    session_id = router.dispatch("POST", base, {}, authorized=True).payload["id"]
    path = f"{base}/{session_id}/validate"
    malformed = router.dispatch(
        "POST", path, {"expected": ["not-a-row"], "actual": []}, authorized=True
    )
    assert malformed.status == 400
    duplicate_keys = router.dispatch(
        "POST",
        path,
        {"expected": [], "actual": [], "key_columns": ["id", "id"]},
        authorized=True,
    )
    assert duplicate_keys.status == 400
    invalid_tolerance = router.dispatch(
        "POST",
        path,
        {"expected": [], "actual": [], "tolerances": {"amount": float("nan")}},
        authorized=True,
    )
    assert invalid_tolerance.status == 400


def test_migration_api_promotes_only_compatible_benchmarks() -> None:
    router = MigrationAPIRouter(MigrationSessionService())
    base = "/v1/workspaces/ws/projects/p/migration/sessions"
    session_id = router.dispatch("POST", base, {}, authorized=True).payload["id"]
    benchmark = {
        "name": "orders",
        "warmup_runs": 1,
        "measured_runs": 3,
        "durations_ms": [10.0, 9.0, 11.0],
        "median_ms": 10.0,
        "fingerprint": "same",
    }
    response = router.dispatch(
        "POST",
        f"{base}/{session_id}/promote",
        {
            "candidate_id": "candidate-1",
            "baseline": benchmark,
            "candidate": {**benchmark, "median_ms": 9.0},
            "semantic_passed": True,
            "quality_passed": True,
        },
        authorized=True,
    )
    assert response.status == 200
    assert response.payload["decision"]["promoted"] is True
    assert response.payload["evidence"]["schema"] == "ronin.migration.optimization-evidence/v1"
    assert response.payload["session"]["promotion_status"] == "promoted"
    assert response.payload["session"]["promotion_digest"]
