from __future__ import annotations

import json
from pathlib import Path

import pytest
from studio_cli import main


def test_doctor_reports_required_local_tools(monkeypatch, capsys) -> None:
    monkeypatch.setattr("studio_cli.shutil.which", lambda name: f"/usr/bin/{name}")

    assert main(["doctor"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert "python>=3.11: ok" in output.out
    assert "git: ok (/usr/bin/git)" in output.out
    assert "docker: ok (/usr/bin/docker)" in output.out
    assert "doctor: all checks passed" in output.out


def test_doctor_fails_closed_when_required_tool_is_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "studio_cli.shutil.which",
        lambda name: None if name == "git" else f"/usr/bin/{name}",
    )

    assert main(["doctor"]) == 2
    output = capsys.readouterr()
    assert "git: fail (not found)" in output.out
    assert "docker: ok (/usr/bin/docker)" in output.out
    assert output.err == "error: doctor required all checks failed\n"


def test_doctor_core_succeeds_without_docker_but_reports_verdict(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "studio_cli.shutil.which",
        lambda name: None if name == "docker" else f"/usr/bin/{name}",
    )

    assert main(["doctor", "--require=core"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert "python>=3.11: ok" in output.out
    assert "git: ok (/usr/bin/git)" in output.out
    assert "docker: fail (not found)" in output.out
    assert "doctor: required core checks passed" in output.out


def test_connectors_capabilities_uses_control_plane_client(monkeypatch, capsys) -> None:
    class _Client:
        def connector_capabilities(self):
            return {"items": [{"connector_id": "http.json"}], "count": 1}

    monkeypatch.setattr("studio_cli._control_plane_client", lambda: _Client())

    assert main(["connectors", "capabilities"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "items": [{"connector_id": "http.json"}],
        "count": 1,
    }


def test_finops_cli_forwards_periods_and_resource_commands(monkeypatch, capsys) -> None:
    class _Client:
        def list_finops_usage(self, workspace_id, *, period_start, period_end):
            assert (workspace_id, period_start, period_end) == (
                "workspace-a",
                "2026-10-24T00:00:00Z",
                "2026-10-25T00:00:00Z",
            )
            return {"items": [{"id": "usage-1"}], "next_cursor": None}

        def list_finops_costs(self, workspace_id, *, period_start, period_end):
            assert (workspace_id, period_start, period_end) == (
                "workspace-a",
                "2026-10-24T00:00:00Z",
                "2026-10-25T00:00:00Z",
            )
            return {"items": [{"usage_id": "usage-1"}], "next_cursor": None}

        def list_finops_budgets(self, workspace_id):
            assert workspace_id == "workspace-a"
            return {"items": [{"id": "budget-1"}], "next_cursor": None}

    monkeypatch.setattr("studio_cli._control_plane_client", lambda: _Client())
    for args, expected in (
        (
            [
                "finops",
                "usage",
                "workspace-a",
                "--period-start",
                "2026-10-24T00:00:00Z",
                "--period-end",
                "2026-10-25T00:00:00Z",
                "--json",
            ],
            "usage-1",
        ),
        (
            [
                "finops",
                "costs",
                "workspace-a",
                "--period-start",
                "2026-10-24T00:00:00Z",
                "--period-end",
                "2026-10-25T00:00:00Z",
                "--json",
            ],
            "usage-1",
        ),
        (["finops", "budgets", "workspace-a", "--json"], "budget-1"),
    ):
        assert main(args) == 0
        output = json.loads(capsys.readouterr().out)
        assert output["items"][0].get("id", output["items"][0].get("usage_id")) == expected


def test_connectors_discover_emits_assets(monkeypatch, capsys) -> None:
    class _Client:
        def connector_discover(
            self, workspace_id, connector_id, connection_ref, *, cursor=None, page_size=None
        ):
            assert workspace_id == "workspace-a"
            assert connector_id == "http.json"
            assert connection_ref == "conn-1"
            assert cursor is None
            assert page_size is None
            return {
                "schema": "ronin.connector-discovery/v1",
                "items": [{"asset_ref": "conn-1::orders"}],
                "count": 1,
            }

    monkeypatch.setattr("studio_cli._control_plane_client", lambda: _Client())

    assert (
        main(
            [
                "connectors",
                "discover",
                "--workspace-id",
                "workspace-a",
                "--connector-id",
                "http.json",
                "--connection-ref",
                "conn-1",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["items"][0]["asset_ref"] == "conn-1::orders"


def test_connectors_discover_passes_page_cursor_and_size(monkeypatch, capsys) -> None:
    class _Client:
        def connector_discover(
            self, workspace_id, connector_id, connection_ref, *, cursor=None, page_size=None
        ):
            assert workspace_id == "workspace-a"
            assert connector_id == "s3.json"
            assert connection_ref == "conn-1"
            assert cursor == "opaque-cursor"
            assert page_size == 25
            return {
                "schema": "ronin.connector-discovery/v1",
                "items": [],
                "count": 0,
                "has_more": False,
                "next_cursor": None,
            }

    monkeypatch.setattr("studio_cli._control_plane_client", lambda: _Client())
    assert (
        main(
            [
                "connectors",
                "discover",
                "--workspace-id",
                "workspace-a",
                "--connector-id",
                "s3.json",
                "--connection-ref",
                "conn-1",
                "--cursor",
                "opaque-cursor",
                "--page-size",
                "25",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["has_more"] is False


def test_connectors_plan_requires_complete_definition(monkeypatch, capsys) -> None:
    monkeypatch.setenv("RONIN_WORKSPACE_ID", "workspace-a")
    monkeypatch.setattr("studio_cli._control_plane_client", lambda: object())

    assert main(["connectors", "plan", "--connector-id", "http.json"]) == 2
    assert "requires --connection-ref" in capsys.readouterr().err


def test_connectors_sync_submit_reads_bounded_definition_and_requires_key(
    monkeypatch, capsys, tmp_path
) -> None:
    definition = {
        "id": "orders-sync",
        "connector_id": "postgres",
        "connection_ref": "conn-1",
        "asset_ref": "conn-1::public.orders",
        "destination_ref": "artifact://orders",
        "checkpoint_identity": "orders-v1",
        "mode": "incremental",
    }
    definition_file = tmp_path / "definition.json"
    definition_file.write_text(json.dumps(definition), encoding="utf-8")

    class _Client:
        def connector_sync_submit(self, workspace_id, project_id, payload, *, idempotency_key):
            assert workspace_id == "workspace-a"
            assert project_id == "project-1"
            assert payload == definition
            assert idempotency_key == "orders-run-1"
            return {"id": "job-1", "state": "queued"}

    monkeypatch.setattr("studio_cli._control_plane_client", lambda: _Client())
    assert (
        main(
            [
                "connectors",
                "sync-submit",
                "--workspace-id",
                "workspace-a",
                "--project-id",
                "project-1",
                "--definition-file",
                str(definition_file),
                "--idempotency-key",
                "orders-run-1",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {"id": "job-1", "state": "queued"}


def test_workspace_and_project_cli_lifecycle_forwards_scopes(monkeypatch, capsys, tmp_path) -> None:
    manifest = {"schema": "ronin.project/v1", "project": {"id": "project-1"}}
    manifest_file = tmp_path / "project.json"
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

    class _Client:
        def list_workspaces(self, *, limit, cursor):
            assert (limit, cursor) == (25, "cursor-1")
            return {"items": [{"id": "workspace-1", "name": "Main"}], "next_cursor": None}

        def create_project(self, workspace_id, payload, *, idempotency_key=None):
            assert (workspace_id, payload, idempotency_key) == ("workspace-1", manifest, "p-1")
            return {"id": "project-1", "name": "ETL"}

        def archive_project(self, workspace_id, project_id, *, idempotency_key):
            assert (workspace_id, project_id, idempotency_key) == (
                "workspace-1",
                "project-1",
                "p-archive",
            )
            return {"archived": True, "project_id": project_id}

    monkeypatch.setattr("studio_cli._control_plane_client", lambda: _Client())
    assert main(["workspaces", "list", "--limit", "25", "--cursor", "cursor-1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["items"][0]["id"] == "workspace-1"
    assert (
        main(
            [
                "projects",
                "create",
                "workspace-1",
                str(manifest_file),
                "--idempotency-key",
                "p-1",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["id"] == "project-1"
    assert (
        main(
            [
                "projects",
                "archive",
                "workspace-1",
                "project-1",
                "--idempotency-key",
                "p-archive",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["archived"] is True


def test_project_bundle_cli_round_trip_uses_bounded_files(monkeypatch, capsys, tmp_path) -> None:
    archive = b"deterministic-bundle"
    exported = tmp_path / "export.roninbundle"
    imported = tmp_path / "import.roninbundle"
    imported.write_bytes(archive)

    class _Client:
        def export_project_bundle_archive(self, workspace_id, project_id):
            assert (workspace_id, project_id) == ("workspace-1", "project-1")
            return archive

        def import_project_bundle_archive(
            self, workspace_id, project_id, payload, *, idempotency_key
        ):
            assert (workspace_id, project_id, payload, idempotency_key) == (
                "workspace-1",
                "project-1",
                archive,
                "bundle-1",
            )
            return {"project": {"id": project_id}, "bundle_digest": "digest"}

    monkeypatch.setattr("studio_cli._control_plane_client", lambda: _Client())
    assert (
        main(
            [
                "projects",
                "bundle-export",
                "workspace-1",
                "project-1",
                "--output",
                str(exported),
            ]
        )
        == 0
    )
    assert exported.read_bytes() == archive
    capsys.readouterr()
    assert (
        main(
            [
                "projects",
                "bundle-import",
                "workspace-1",
                "project-1",
                str(imported),
                "--idempotency-key",
                "bundle-1",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["project"]["id"] == "project-1"


@pytest.mark.parametrize("command", ["sync-status", "sync-cancel"])
def test_connectors_sync_status_and_cancel_forward_resource_scope(
    monkeypatch, capsys, command
) -> None:
    class _Client:
        def connector_sync_status(self, workspace_id, project_id, job_id):
            assert (workspace_id, project_id, job_id) == ("workspace-a", "project-1", "job-1")
            return {"job": {"id": job_id, "state": "succeeded"}}

        def connector_sync_cancel(self, workspace_id, project_id, job_id):
            assert (workspace_id, project_id, job_id) == ("workspace-a", "project-1", "job-1")
            return {"id": job_id, "state": "cancellation_requested"}

    monkeypatch.setattr("studio_cli._control_plane_client", lambda: _Client())
    assert (
        main(
            [
                "connectors",
                command,
                "--workspace-id",
                "workspace-a",
                "--project-id",
                "project-1",
                "--job-id",
                "job-1",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["job" if command == "sync-status" else "id"] == (
        {"id": "job-1", "state": "succeeded"} if command == "sync-status" else "job-1"
    )


def test_doctor_all_still_requires_docker(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "studio_cli.shutil.which",
        lambda name: None if name == "docker" else f"/usr/bin/{name}",
    )

    assert main(["doctor", "--require=all"]) == 2
    output = capsys.readouterr()
    assert "docker: fail (not found)" in output.out
    assert output.err == "error: doctor required all checks failed\n"


def test_validate_and_plan_reuse_canonical_demo_contracts(capsys) -> None:
    assert main(["validate", "examples/demo"]) == 0
    validate_output = capsys.readouterr()
    assert "notebooks: 1" in validate_output.out
    assert "validate: ok" in validate_output.out

    assert main(["plan", "examples/demo", "-t", "notebooks/etl"]) == 0
    plan_output = capsys.readouterr()
    assert "target: notebooks/etl.ronin.json" in plan_output.out
    assert "1. extract-customers" in plan_output.out
    assert "2. extract-orders" in plan_output.out
    assert "3. join-and-aggregate" in plan_output.out
    assert "4. quality-check" in plan_output.out
    assert "5. publish" in plan_output.out
    assert "0: extract-customers, extract-orders" in plan_output.out
    assert "1: join-and-aggregate" in plan_output.out
    assert "2: quality-check" in plan_output.out
    assert "3: publish" in plan_output.out


def test_help_exposes_evidence_as_first_class_command(capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])
    assert raised.value.code == 0
    output = capsys.readouterr()
    assert "evidence" in output.out


def test_evidence_help_comes_from_canonical_parser(capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["evidence", "--help"])
    assert raised.value.code == 0
    output = capsys.readouterr()
    assert "usage: ronin evidence" in output.out
    assert "job_id" in output.out
    assert "--json" in output.out


@pytest.mark.parametrize("target", ["../outside", "/outside", " missing "])
def test_plan_rejects_unsafe_or_malformed_targets(target: str, capsys) -> None:
    assert main(["plan", "examples/demo", "-t", target]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.startswith("error: ")


def test_validate_rejects_invalid_notebook_dependencies(tmp_path: Path, capsys) -> None:
    project = tmp_path / "project"
    notebooks = project / "notebooks"
    ronin_dir = project / ".ronin"
    notebooks.mkdir(parents=True)
    ronin_dir.mkdir()

    source_manifest = Path("examples/demo/.ronin/project.json").read_text(encoding="utf-8")
    (ronin_dir / "project.json").write_text(source_manifest, encoding="utf-8")
    source_notebook = json.loads(
        Path("examples/demo/notebooks/etl.ronin.json").read_text(encoding="utf-8")
    )
    source_notebook["cells"][1]["dependencies"] = ["missing-cell"]
    (notebooks / "broken.ronin.json").write_text(
        json.dumps(source_notebook),
        encoding="utf-8",
    )

    assert main(["validate", str(project)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "invalid notebook dependencies" in output.err


def test_validate_rejects_missing_project(capsys) -> None:
    assert main(["validate", "does-not-exist"]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "error: project does not exist: does-not-exist\n"


def test_migrate_inventory_writes_canonical_report(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.json"
    output = tmp_path / "report.json"
    source.write_text('{"objects":[{"type":"job","id":"job-1"}]}', encoding="utf-8")
    assert main(["migrate", "inventory", "databricks", str(source), "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["source_platform"] == "databricks"
    assert "migration report written" in capsys.readouterr().out
