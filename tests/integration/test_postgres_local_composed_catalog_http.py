from __future__ import annotations

import http.client
import json
import os
import socket
from uuid import uuid4

import pytest
from studio_cli.local_composed import build_local_composed_from_env
from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    DataContract,
    OwnershipMetadata,
    QualityRule,
    QualityRuleId,
    SensitivityMetadata,
    WorkspaceId,
)
from studio_observability import AlertRule, SqliteTelemetryStore
from studio_orchestrator import Instant

_DSN = os.environ.get("RONIN_TEST_POSTGRES_DSN")
if not _DSN:
    pytest.skip("RONIN_TEST_POSTGRES_DSN is not configured", allow_module_level=True)

psycopg = pytest.importorskip("psycopg")


def _unused_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _request(
    address: tuple[str, int], method: str, path: str, *, body: object | None = None
) -> tuple[int, dict[str, object]]:
    payload = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    headers = {"Authorization": "Bearer postgres-catalog-http-test"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    connection = http.client.HTTPConnection(*address, timeout=5)
    try:
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


def test_postgres_composition_serves_catalog_and_governance_over_real_http(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    workspace_id = WorkspaceId(f"catalog-http-{uuid4().hex}")
    monkeypatch.setenv("RONIN_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("RONIN_POSTGRES_DSN", _DSN)
    monkeypatch.setenv("RONIN_DB", str(tmp_path / "ronin.sqlite3"))
    monkeypatch.setenv("RONIN_WORKSPACE_ID", str(workspace_id))
    monkeypatch.setenv("RONIN_HOST", "127.0.0.1")
    monkeypatch.setenv("RONIN_PORT", str(_unused_port()))
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", str(_unused_port()))
    monkeypatch.setenv("RONIN_CONTROL_PLANE_TOKEN", "postgres-catalog-http-test")
    monkeypatch.setenv(
        "RONIN_CONTROL_PLANE_PERMISSIONS",
        "scheduler.read,scheduler.write,workspace.read,workspace.write,workspace.admin,project.read,project.write",
    )
    monkeypatch.setenv("RONIN_TOKEN", "postgres-catalog-jobs-test")
    monkeypatch.setenv(
        "RONIN_TOKEN_SCOPES",
        '{"version":1,"grants":[{"actions":["cancel","evidence:read","execute",'
        '"events","list","read","submit"],"constraints":{},"resource":{"identifier":null,'
        '"kind":"*"},"version":1}]}',
    )

    workspace_text = str(workspace_id)
    asset = CatalogAsset(AssetId("orders"), "table", "Orders", tags=("sales",))
    following_asset = CatalogAsset(AssetId("orders-archive"), "table", "Orders archive")
    sensitivity = SensitivityMetadata(1, explicit=("internal",))
    ownership = OwnershipMetadata(1, "group/data", ("user/steward",), "sales")
    revision = AssetRevision(AssetRef(asset.id, AssetVersion("1")), schema_digest="orders-v1")
    contract = DataContract(
        revision.ref,
        "exact",
        (
            QualityRule(
                QualityRuleId("non-empty"),
                "row_count",
                "At least one order",
                blocking=True,
                parameters=(("min", "1"),),
            ),
        ),
    )
    alert_rule = AlertRule(
        "quality-run-failed",
        "Quality run failures",
        "quality.run.failure",
        "gte",
        1.0,
        (("asset", "orders@1"),),
    )
    composition = None

    try:
        composition = build_local_composed_from_env()
        address = composition.control_plane_server.server_address
        assert composition.control_plane_server.catalog_reader is not None
        assert composition.control_plane_server.alert_reader is not None
        telemetry = SqliteTelemetryStore(tmp_path / "ronin.sqlite3")
        telemetry.put_alert_rule(alert_rule)
        composition.start()

        status, payload = _request(
            address,
            "GET",
            f"/v1/workspaces/{workspace_text}/alerts/rules",
        )
        assert status == 200, payload
        assert payload["items"] == [alert_rule.to_payload()]

        status, payload = _request(
            address,
            "POST",
            f"/v1/workspaces/{workspace_text}/alerts/evaluate",
            body={"rule_id": "quality-run-failed"},
        )
        assert status == 200, payload
        assert payload["changed"] is False
        assert payload["metric"] is None
        assert payload["state"] is None

        status, payload = _request(
            address,
            "POST",
            f"/v1/workspaces/{workspace_text}/catalog/assets",
            body=asset.to_payload(),
        )
        assert status == 201, payload
        assert payload == asset.to_payload()

        status, payload = _request(
            address,
            "POST",
            f"/v1/workspaces/{workspace_text}/catalog/assets",
            body=following_asset.to_payload(),
        )
        assert status == 201, payload
        assert payload == following_asset.to_payload()

        for name, metadata in (("sensitivity", sensitivity), ("ownership", ownership)):
            status, payload = _request(
                address,
                "POST",
                f"/v1/workspaces/{workspace_text}/catalog/assets/orders/{name}",
                body=metadata.to_payload(),
            )
            assert status == 201, payload
            assert payload == metadata.to_payload()

        status, payload = _request(
            address,
            "GET",
            f"/v1/workspaces/{workspace_text}/catalog/assets?limit=1&include_governance=true",
        )
        assert status == 200, payload
        assert payload["items"] == [
            {
                **asset.to_payload(),
                "sensitivity": sensitivity.to_payload(),
                "ownership": ownership.to_payload(),
            }
        ]
        next_cursor = payload["next_cursor"]
        assert isinstance(next_cursor, str)
        assert next_cursor
        status, payload = _request(
            address,
            "GET",
            f"/v1/workspaces/{workspace_text}/catalog/assets?limit=1&include_governance=true&cursor={next_cursor}",
        )
        assert status == 200, payload
        assert payload == {
            "items": [
                {
                    **following_asset.to_payload(),
                    "sensitivity": None,
                    "ownership": None,
                }
            ],
            "next_cursor": None,
        }

        catalog_reader = composition.control_plane_server.catalog_reader
        assert catalog_reader is not None
        assert callable(getattr(catalog_reader, "put_revision", None))
        catalog_reader.put_revision(
            workspace_id, revision, now=Instant("2026-10-24T00:00:00.000000Z")
        )
        status, payload = _request(
            address,
            "PUT",
            f"/v1/workspaces/{workspace_text}/quality/contracts/orders/1",
            body=contract.to_payload(),
        )
        assert status == 200, payload
        assert payload == contract.to_payload()

        status, payload = _request(
            address,
            "POST",
            f"/v1/workspaces/{workspace_text}/quality/runs",
            body={
                "asset": {"asset_id": "orders", "version": "1"},
                "rows": [{"id": 1}],
                "run_id": "quality-http-passed",
                "contract_digest": contract.digest,
                "enforce_blocking": True,
            },
        )
        assert status == 201, payload
        assert payload["gate_passed"] is True
        assert payload["run"]["status"] == "passed"

        status, payload = _request(
            address,
            "GET",
            f"/v1/workspaces/{workspace_text}/alerts/instances",
        )
        assert status == 200, payload
        assert payload["items"] == []

        failed_request = {
            "asset": {"asset_id": "orders", "version": "1"},
            "rows": [],
            "run_id": "quality-http-failed",
            "contract_digest": contract.digest,
            "enforce_blocking": False,
        }
        status, payload = _request(
            address,
            "POST",
            f"/v1/workspaces/{workspace_text}/quality/runs",
            body=failed_request,
        )
        assert status == 201, payload
        assert payload["gate_passed"] is False
        assert payload["run"]["status"] == "failed"
        failed_payload = payload

        status, payload = _request(
            address,
            "GET",
            f"/v1/workspaces/{workspace_text}/alerts/instances",
        )
        assert status == 200, payload
        assert len(payload["items"]) == 1
        status, payload = _request(
            address,
            "POST",
            f"/v1/workspaces/{workspace_text}/alerts/evaluate",
            body={"rule_id": "quality-run-failed"},
        )
        assert status == 200, payload
        assert payload["changed"] is False
        assert payload["state"]["status"] == "open"

        status, replay_payload = _request(
            address,
            "POST",
            f"/v1/workspaces/{workspace_text}/quality/runs",
            body=failed_request,
        )
        assert status == 201, replay_payload
        assert replay_payload == failed_payload
        assert len(telemetry.list_metrics()) == 4

        status, payload = _request(
            address,
            "GET",
            f"/v1/workspaces/{workspace_text}/quality/state/orders/1",
        )
        assert status == 200, payload
        assert payload["latest_run_id"] == "quality-http-failed"
        assert payload["latest_status"] == "failed"
        assert [item["status"] for item in payload["history"]] == ["passed", "failed"]
    finally:
        if composition is not None:
            composition.stop()
        with psycopg.connect(_DSN, autocommit=True) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.ronin_workspaces')")
            if cursor.fetchone()[0] is not None:
                cursor.execute(
                    "DELETE FROM ronin_workspaces WHERE workspace_id=%s", (workspace_text,)
                )
