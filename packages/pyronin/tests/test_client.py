from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.error import URLError

import pytest
from pyronin import (
    DeploymentBinding,
    HTTPTransport,
    JobState,
    OwnershipMetadata,
    ProjectEnvironmentBindings,
    ProtocolError,
    Ronin,
    SensitivityMetadata,
    TransportError,
)


@dataclass
class FakeTransport:
    responses: list[object]
    calls: list[
        tuple[
            str,
            str,
            Mapping[str, object] | None,
            Mapping[str, str] | None,
            Mapping[str, str] | None,
        ]
    ] = field(default_factory=list)

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        query: Mapping[str, str] | None = None,
    ) -> object:
        self.calls.append((method, path, payload, headers, query))
        return self.responses.pop(0)


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


class _FlakyOpener:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def open(self, _request: object, *, timeout: float) -> _Response:
        assert timeout > 0
        self.calls += 1
        if self.calls <= self.failures:
            raise URLError("synthetic outage")
        return _Response(b'{"ok":true}')


def _job_payload(state: str) -> dict[str, object]:
    return {"id": "job/a", "state": state, "failure_code": None}


def test_submit_status_cancel_events_and_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = FakeTransport(
        [
            _job_payload("queued"),
            _job_payload("running"),
            {
                "items": [
                    {
                        "sequence": 0,
                        "attempt_id": "attempt-1",
                        "attempt_sequence": 0,
                        "kind": "job.started",
                        "message": "running",
                        "occurred_at": "2026-09-07T11:00:00.000000Z",
                    }
                ],
                "next_since": "next-events",
            },
            _job_payload("cancelling"),
            _job_payload("running"),
            _job_payload("succeeded"),
        ]
    )
    client = Ronin(transport=transport)
    job = client.submit(project="demo", target="etl", idempotency_key="once")
    assert job.id == "job/a"
    assert job.status() is JobState.RUNNING
    events = job.events(limit=25)
    assert events.items[0].kind == "job.started"
    assert events.items[0].attempt_id == "attempt-1"
    assert events.next_since == "next-events"
    assert transport.calls[2][4] == {"limit": "25"}
    assert job.cancel().state is JobState.CANCELLING
    monkeypatch.setattr("pyronin.time.sleep", lambda _: None)
    assert job.wait(poll_interval=0.01).state is JobState.SUCCEEDED
    assert transport.calls[0][3] == {"Idempotency-Key": "once"}


def test_workspace_and_project_lifecycle_reads_are_typed_and_scoped() -> None:
    transport = FakeTransport(
        [
            {"items": [{"id": "ws-1", "name": "Main", "version": 2}]},
            {"workspace": {"id": "ws-1", "name": "Main", "status": "active"}},
            {"items": [{"id": "project-1", "name": "ETL", "version": 4}]},
            {"project": {"id": "project-1", "name": "ETL", "status": "active"}},
            {"workspace": {"id": "ws-1", "name": "Main", "status": "archived"}},
        ]
    )
    client = Ronin(transport=transport)

    assert client.list_workspaces()[0].version == 2
    assert client.get_workspace("ws-1").id == "ws-1"
    assert client.list_projects("ws-1")[0].id == "project-1"
    assert client.get_project("ws-1", "project-1").name == "ETL"
    assert client.archive_workspace("ws-1").status == "archived"
    assert transport.calls[2][1] == "/v1/workspaces/ws-1/projects"
    assert transport.calls[3][1] == "/v1/workspaces/ws-1/projects/project-1"


def test_create_workspace_uses_idempotency_header() -> None:
    transport = FakeTransport(
        [{"id": "ws-2", "name": "Analytics", "description": None, "state": "active"}]
    )
    workspace = Ronin(transport=transport).create_workspace(
        "ws-2", name="Analytics", idempotency_key="create-ws-2"
    )
    assert workspace.id == "ws-2"
    assert transport.calls[0][0:3] == (
        "POST",
        "/v1/workspaces",
        {"id": "ws-2", "name": "Analytics", "description": None},
    )
    assert transport.calls[0][3] == {"Idempotency-Key": "create-ws-2"}


def test_import_migration_session_is_typed_and_scoped() -> None:
    transport = FakeTransport(
        [
            {
                "status": "importable",
                "import_digest": "i" * 64,
                "project_digest": "p" * 64,
                "target": "project-catalog",
            }
        ]
    )
    evidence = Ronin(transport=transport).import_migration_session(
        "ws/1", "project/1", "migration/1", target="project-catalog"
    )
    assert evidence.status == "importable"
    assert evidence.project_digest == "p" * 64
    assert transport.calls[0][1] == (
        "/v1/workspaces/ws%2F1/projects/project%2F1/"
        "migration/sessions/migration%2F1/import"
    )


def test_create_migration_session_uses_idempotency_header() -> None:
    transport = FakeTransport(
        [{"id": "migration-1", "workspace_id": "ws-1", "project_id": "p-1", "state": "draft"}]
    )
    session = Ronin(transport=transport).create_migration_session(
        "ws-1", "p-1", idempotency_key="migration-create-1"
    )
    assert session.state == "draft"
    assert transport.calls[0][0:3] == (
        "POST",
        "/v1/workspaces/ws-1/projects/p-1/migration/sessions",
        {},
    )
    assert transport.calls[0][3] == {"Idempotency-Key": "migration-create-1"}


def test_list_migration_sessions_forwards_bounded_cursor() -> None:
    transport = FakeTransport(
        [
            {
                "items": [
                    {
                        "id": "m-1",
                        "workspace_id": "ws-1",
                        "project_id": "p-1",
                        "state": "draft",
                    }
                ],
                "next_cursor": "next-1",
            }
        ]
    )
    page = Ronin(transport=transport).list_migration_sessions(
        "ws-1", "p-1", limit=1, cursor="start-1"
    )
    assert page.items[0].id == "m-1"
    assert page.next_cursor == "next-1"
    assert transport.calls[0][4] == {"limit": "1", "cursor": "start-1"}


def test_discover_migration_session_encodes_document_and_validates_inventory() -> None:
    transport = FakeTransport([{"units": [{"key": "job:j-1"}], "digest": "d" * 64}])
    payload = Ronin(transport=transport).discover_migration_session(
        "ws-1", "p-1", "m-1", profile="databricks", document=b'{"jobs":[]}', source_version="15.4"
    )
    assert payload["units"] == [{"key": "job:j-1"}]
    assert transport.calls[0][2]["profile"] == "databricks"
    assert transport.calls[0][2]["document_base64"] == "eyJqb2JzIjpbXX0="


def test_convert_migration_session_requires_workflow_and_report() -> None:
    transport = FakeTransport([{"workflow": {"id": "wf-1"}, "report": {"objects": []}}])
    payload = Ronin(transport=transport).convert_migration_session(
        "ws-1", "p-1", "m-1", profile="fabric", document=b"{}", source_version="2026"
    )
    assert payload["workflow"]["id"] == "wf-1"
    assert transport.calls[0][0:2] == (
        "POST",
        "/v1/workspaces/ws-1/projects/p-1/migration/sessions/m-1/convert",
    )


def test_qualify_migration_session_validates_findings_contract() -> None:
    transport = FakeTransport([{"status": "passed", "files_checked": 2, "findings": []}])
    payload = Ronin(transport=transport).qualify_migration_session("ws-1", "p-1", "m-1")
    assert payload["status"] == "passed"
    assert payload["files_checked"] == 2


def test_workspace_and_project_pages_forward_and_validate_cursor() -> None:
    transport = FakeTransport(
        [
            {"items": [{"id": "ws-2", "name": "Next"}], "next_cursor": "w-next"},
            {"items": [{"id": "p-2", "name": "Next project"}], "next_cursor": None},
        ]
    )
    client = Ronin(transport=transport)

    workspaces = client.list_workspaces_page(limit=1, cursor="w-start")
    projects = client.list_projects_page("ws-1", limit=1, cursor="p-start")

    assert workspaces.items[0].id == "ws-2"
    assert workspaces.next_cursor == "w-next"
    assert projects.items[0].id == "p-2"
    assert projects.next_cursor is None
    assert transport.calls[0][4] == {"limit": "1", "cursor": "w-start"}
    assert transport.calls[1][4] == {"limit": "1", "cursor": "p-start"}

    with pytest.raises(ValueError, match="cursor"):
        client.list_workspaces_page(cursor=" ")


def test_environment_binding_lifecycle_is_typed_and_scoped() -> None:
    transport = FakeTransport(
        [
            {
                "project_id": "p-1",
                "environment_id": "dev",
                "bindings": [
                    {"kind": "connection", "source_ref": "main", "target_ref": "connection://dev"}
                ],
            },
            {
                "project_id": "p-1",
                "environment_id": "dev",
                "bindings": [],
            },
        ]
    )
    client = Ronin(transport=transport)
    current = client.get_environment_bindings("ws-1", "p-1", "dev")
    updated = client.put_environment_bindings(
        "ws-1",
        ProjectEnvironmentBindings(
            "p-1", "dev", (DeploymentBinding("connection", "main", "connection://dev"),)
        ),
    )
    assert current.bindings[0].target_ref == "connection://dev"
    assert updated.bindings == ()
    assert transport.calls[0][1].endswith("/environments/dev/bindings")
    assert transport.calls[1][0] == "PUT"


def test_alert_operations_are_scoped_and_validate_response() -> None:
    transport = FakeTransport(
        [
            {"items": [{"id": "rule-1", "metric_name": "queue"}]},
            {"rule_id": "rule-1", "changed": True, "metric": None, "state": None},
            {"rule_id": "rule-1", "acknowledged": True},
        ]
    )
    client = Ronin(transport=transport)

    assert client.list_alert_rules("ws-1")[0]["id"] == "rule-1"
    assert client.evaluate_alert("ws-1", "rule-1")["changed"] is True
    assert client.acknowledge_alert("ws-1", "rule-1", "fingerprint-1")["acknowledged"]
    assert transport.calls[0][1] == "/v1/workspaces/ws-1/alerts/rules"
    assert transport.calls[1][1] == "/v1/workspaces/ws-1/alerts/evaluate"
    assert transport.calls[1][2] == {"rule_id": "rule-1"}
    assert transport.calls[2][1] == "/v1/workspaces/ws-1/alerts/acknowledge"
    assert transport.calls[2][2] == {"rule_id": "rule-1", "fingerprint": "fingerprint-1"}


def test_ml_feature_definition_api_is_scoped_and_versioned() -> None:
    transport = FakeTransport(
        [
            {"items": [{"id": "features/customer", "version": 1}]},
            {"id": "features/customer", "version": 1},
            {"items": [{"id": "features/customer", "version": 1}]},
        ]
    )
    client = Ronin(transport=transport)
    definition = {"id": "features/customer", "version": 1}
    assert client.list_ml_feature_definitions("ws-1")[0]["id"] == "features/customer"
    assert client.publish_ml_feature_definition("ws-1", definition)["version"] == 1
    assert client.get_ml_feature_definition("ws-1", "features/customer", 1)["version"] == 1
    assert transport.calls[0][4] == {"workspace_id": "ws-1"}
    assert transport.calls[1][4] == {"workspace_id": "ws-1"}


def test_semantic_join_returns_typed_query_result() -> None:
    transport = FakeTransport(
        [{"columns": [{"name": "customer_id", "type": "string"}], "rows": [["c-1"]]}]
    )
    result = Ronin(transport=transport).join_semantic(
        "ws-1", "project-1", {"left_model": "customers", "right_model": "orders"}
    )
    assert result.columns[0].name == "customer_id"
    assert result.columns[0].type_name == "string"
    assert result.rows == (("c-1",),)
    assert transport.calls[0][1].endswith("/semantic/join")


def test_streaming_health_rejects_boolean_counters_and_empty_digest() -> None:
    for payload in (
        {
            "stream_id": "stream-1",
            "checkpoint_digest": "sha256:ok",
            "partitions": True,
            "lag": {},
            "total_lag": 0,
            "healthy": True,
        },
        {
            "stream_id": "stream-1",
            "checkpoint_digest": "sha256:ok",
            "partitions": 1,
            "lag": {"0": True},
            "total_lag": 0,
            "healthy": True,
        },
        {
            "stream_id": "stream-1",
            "checkpoint_digest": " ",
            "partitions": 1,
            "lag": {},
            "total_lag": 0,
            "healthy": True,
        },
    ):
        with pytest.raises(ProtocolError):
            Ronin(transport=FakeTransport([payload])).streaming_health("ws-1", "stream-1")


def test_finops_sdk_methods_scope_and_forward_periods() -> None:
    transport = FakeTransport(
        [
            {"items": [{"metric": "cpu"}]},
            {"items": [{"cost": 12.5}]},
            {"items": [{"budget": "monthly"}]},
        ]
    )
    client = Ronin(transport=transport)
    assert (
        client.list_finops_usage("ws-1", period_start="2026-01-01", period_end="2026-01-31")[0][
            "metric"
        ]
        == "cpu"
    )
    assert (
        client.list_finops_costs("ws-1", period_start="2026-01-01", period_end="2026-01-31")[0][
            "cost"
        ]
        == 12.5
    )
    assert client.list_finops_budgets("ws-1")[0]["budget"] == "monthly"
    assert transport.calls[0][4] == {"period_start": "2026-01-01", "period_end": "2026-01-31"}


def test_graph_sdk_operations_forward_limits_and_payloads() -> None:
    transport = FakeTransport(
        [
            {"rows": [{"id": "o-1"}]},
            {"items": [{"object_type": "Customer", "key": [["id", "1"]]}]},
            {"items": [{"object_type": "Order", "key": [["id", "2"]]}]},
            {"accepted": True},
        ]
    )
    client = Ronin(transport=transport)
    assert client.query_graph("ws-1", "graph-1", "SELECT *", max_limit=10)["rows"]
    assert (
        client.list_graph_objects("ws-1", "graph-1", "Customer", limit=3)[0]["object_type"]
        == "Customer"
    )
    assert (
        client.graph_neighbors("ws-1", "graph-1", "Customer", [["id", "1"]])[0]["object_type"]
        == "Order"
    )
    assert client.execute_graph_action("ws-1", "graph-1", {"action": "refresh"})["accepted"]
    assert transport.calls[1][4] == {"limit": "3"}
    assert transport.calls[2][2]["key"] == [["id", "1"]]


def test_ontology_sdk_reads_versions_and_schema() -> None:
    transport = FakeTransport(
        [
            {"items": [{"version": "1"}]},
            {"id": "orders", "version": "1", "objects": []},
        ]
    )
    client = Ronin(transport=transport)
    assert client.list_ontology_versions("ws-1", "orders")[0]["version"] == "1"
    assert client.get_ontology_schema("ws-1", "orders", "1")["id"] == "orders"
    assert transport.calls[1][1].endswith("/ontologies/orders/1")


def test_catalog_revision_sdk_reads_list_and_version() -> None:
    transport = FakeTransport(
        [{"items": [{"version": "1"}]}, {"asset_id": "orders", "version": "1"}]
    )
    client = Ronin(transport=transport)
    assert client.list_catalog_revisions("ws-1", "orders")[0]["version"] == "1"
    assert client.get_catalog_revision("ws-1", "orders", "1")["asset_id"] == "orders"
    assert transport.calls[1][1].endswith("/catalog/assets/orders/revisions/1")


def test_glossary_listing_forwards_optional_search_query() -> None:
    transport = FakeTransport([{"items": []}])
    assert Ronin(transport=transport).list_glossary_terms("ws-1", query="customer", limit=7) == ()
    assert transport.calls[0][4] == {"limit": "7", "q": "customer"}
    with pytest.raises(ValueError, match="query"):
        Ronin(transport=FakeTransport([])).list_glossary_terms("ws-1", query=" ")


def test_deployment_binding_rejects_unknown_scheme_and_credentials() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        DeploymentBinding("unknown", "source", "unknown://target")
    with pytest.raises(ValueError, match="credential"):
        DeploymentBinding("secret", "source", "secret://user:password@example")


def test_alert_instance_listing_uses_structured_query_parameters() -> None:
    transport = FakeTransport([{"items": [{"id": "instance-1"}]}])
    instances = Ronin(transport=transport).list_alert_instances("ws-1", limit=7)
    assert instances[0]["id"] == "instance-1"
    assert transport.calls[0][1] == "/v1/workspaces/ws-1/alerts/instances"
    assert transport.calls[0][4] == {"limit": "7"}


def test_workspace_and_project_mutations_forward_idempotency_and_etag() -> None:
    transport = FakeTransport(
        [
            {"workspace": {"id": "ws-1", "name": "Renamed"}},
            {"project": {"id": "project-1", "name": "ETL"}},
            {"project": {"id": "project-1", "name": "Updated"}},
            {"unregistered": True, "project_id": "project-1"},
        ]
    )
    client = Ronin(transport=transport)

    assert client.update_workspace("ws-1", name="Renamed", if_match='"old"').name == "Renamed"
    assert (
        client.create_project("ws-1", {"id": "project-1", "name": "ETL"}, idempotency_key="p-1").id
        == "project-1"
    )
    assert (
        client.update_project(
            "ws-1", "project-1", {"id": "project-1", "name": "Updated"}, if_match='"etag"'
        ).name
        == "Updated"
    )
    assert client.delete_project("ws-1", "project-1") is True
    assert transport.calls[0][3] == {"If-Match": '"old"'}
    assert transport.calls[1][3] == {"Idempotency-Key": "p-1"}
    assert transport.calls[2][3] == {"If-Match": '"etag"'}


def test_environment_lifecycle_and_diff_use_canonical_paths() -> None:
    transport = FakeTransport(
        [
            {"items": [{"id": "env/1", "name": "Prod", "state": "active"}]},
            {"environment": {"id": "env/1", "name": "Prod"}},
            {"environment": {"id": "env/1", "name": "Prod"}},
            {"environment": {"id": "env/1", "name": "Prod", "state": "disabled"}},
            {"changed": True, "fields": ["description"]},
        ]
    )
    client = Ronin(transport=transport)

    assert client.list_environments("ws/1")[0].id == "env/1"
    assert client.get_environment("ws/1", "env/1").name == "Prod"
    assert client.create_environment("ws/1", {"id": "env/1", "name": "Prod"}).id == "env/1"
    assert client.disable_environment("ws/1", "env/1").state == "disabled"
    assert client.diff_environment("ws/1", "env/1", {"id": "env/1"})["changed"] is True
    assert transport.calls[0][1] == "/v1/workspaces/ws%2F1/environments"
    assert transport.calls[4][1].endswith("/env%2F1/diff")


def test_role_binding_administration_is_typed_and_path_scoped() -> None:
    transport = FakeTransport(
        [
            {
                "items": [
                    {
                        "workspace_id": "ws-1",
                        "subject_kind": "principal",
                        "subject_id": "u/1",
                        "role": "viewer",
                    }
                ]
            },
            {
                "workspace_id": "ws-1",
                "subject_kind": "principal",
                "subject_id": "u/1",
                "role": "editor",
            },
            {"removed": True},
        ]
    )
    client = Ronin(transport=transport)
    assert client.list_role_bindings()[0].role == "viewer"
    assert client.put_role_binding("principal", "u/1", "editor").role == "editor"
    assert client.delete_role_binding("principal", "u/1", "editor") is True
    assert "/principal/u%2F1/editor" in transport.calls[1][1]


def test_security_principal_and_group_reads_are_typed_and_path_scoped() -> None:
    transport = FakeTransport(
        [
            {
                "items": [
                    {
                        "id": "u/1",
                        "kind": "user",
                        "display_name": "Alice",
                        "issuer": "oidc",
                        "subject": "alice",
                        "active": True,
                    }
                ]
            },
            {
                "id": "u/1",
                "kind": "user",
                "display_name": "Alice",
                "issuer": "oidc",
                "subject": "alice",
                "active": True,
            },
            {"items": [{"id": "team", "name": "Team"}]},
            {"id": "team", "name": "Team"},
        ]
    )
    client = Ronin(transport=transport)
    assert client.list_security_principals()[0].id == "u/1"
    assert client.get_security_principal("u/1").subject == "alice"
    assert client.list_security_groups()[0].name == "Team"
    assert client.get_security_group("team").name == "Team"
    assert transport.calls[1][1] == "/v1/admin/security/principals/u%2F1"
    assert transport.calls[3][1] == "/v1/admin/security/groups/team"


def test_security_principal_group_and_membership_mutations_are_typed() -> None:
    principal = {
        "id": "u/1",
        "kind": "user",
        "display_name": "Alice",
        "issuer": "oidc",
        "subject": "alice",
        "active": True,
    }
    transport = FakeTransport(
        [
            principal,
            {"id": "team", "name": "Team"},
            {"member": True},
            {"items": [principal]},
            {"member": False},
        ]
    )
    client = Ronin(transport=transport)
    assert client.put_security_principal("u/1", principal).id == "u/1"
    assert client.put_security_group("team", "Team").name == "Team"
    assert client.add_security_group_member("team", "u/1") is True
    assert client.list_security_group_members("team")[0].id == "u/1"
    assert client.remove_security_group_member("team", "u/1") is True
    assert transport.calls[2][1].endswith("/groups/team/members/u%2F1")


def test_catalog_assets_are_parsed_and_query_is_encoded() -> None:
    transport = FakeTransport(
        [{"items": [{"id": "asset-1", "kind": "table", "name": "orders", "tags": ["gold"]}]}]
    )
    assets = Ronin(transport=transport).list_catalog_assets("workspace/1", query="orders", limit=10)
    assert assets[0].name == "orders"
    assert assets[0].tags == ("gold",)
    assert transport.calls[0][1] == "/v1/workspaces/workspace%2F1/catalog/assets"
    assert transport.calls[0][4] == {"limit": "10", "q": "orders"}


def test_compare_pipeline_revisions_uses_structured_query() -> None:
    transport = FakeTransport([{"changed": ["steps[0]"]}])

    result = Ronin(transport=transport).compare_pipeline_revisions(
        "workspace/1", "project/1", "pipeline/1", 3, 7
    )

    assert result == {"changed": ["steps[0]"]}
    assert transport.calls[0][1] == (
        "/v1/workspaces/workspace%2F1/projects/project%2F1/pipelines/pipeline%2F1/revisions/compare"
    )
    assert transport.calls[0][4] == {"left_revision": "3", "right_revision": "7"}


def test_glossary_terms_round_trip_and_encode_identity() -> None:
    term = {
        "id": "customer/id",
        "version": "1",
        "name": "Customer",
        "definition": "A paying account.",
        "owner": "data-team",
        "references": ["catalog:customer"],
    }
    transport = FakeTransport([{"items": [term]}, term, term, term])
    client = Ronin(transport=transport)
    assert client.list_glossary_terms("workspace/1")[0].name == "Customer"
    assert client.get_glossary_term("workspace/1", "customer/id", "1").owner == "data-team"
    stored = client.get_glossary_term("workspace/1", "customer/id", "1")
    assert client.put_glossary_term("workspace/1", stored).version == "1"
    assert transport.calls[0][1] == "/v1/workspaces/workspace%2F1/glossary/terms"
    assert transport.calls[1][1].endswith("/glossary/terms/customer%2Fid/1")


def test_catalog_ownership_is_encoded_and_parsed() -> None:
    transport = FakeTransport(
        [
            {
                "version": 2,
                "owner_ref": "group/platform",
                "steward_refs": ["user/steward"],
                "domain": "sales",
                "lifecycle": "active",
            }
        ]
    )
    result = Ronin(transport=transport).put_catalog_ownership(
        "workspace/1",
        "asset/orders",
        OwnershipMetadata(2, "group/platform", ("user/steward",), "sales"),
    )
    assert result.version == 2
    assert transport.calls[0][1].endswith("/catalog/assets/asset%2Forders/ownership")


def test_catalog_lineage_is_bounded_and_directional() -> None:
    transport = FakeTransport(
        [
            {
                "items": [
                    {
                        "source": {"id": "a"},
                        "target": {"id": "b"},
                        "operation": "transform",
                        "mode": "observed",
                        "execution_ref": "run-1",
                        "column_mappings": [],
                    }
                ],
            }
        ]
    )
    edges = Ronin(transport=transport).list_catalog_lineage(
        "workspace/1", "asset/orders", "1", direction="downstream"
    )
    assert edges[0].execution_ref == "run-1"
    assert transport.calls[0][4] == {"direction": "downstream"}


def test_catalog_sensitivity_preserves_explicit_and_inherited_labels() -> None:
    transport = FakeTransport(
        [
            {
                "version": 3,
                "explicit": ["restricted"],
                "inherited": ["internal"],
                "inherited_from": ["asset/parent"],
                "effective": ["internal", "restricted"],
            }
        ]
    )
    result = Ronin(transport=transport).put_catalog_sensitivity(
        "workspace",
        "asset/child",
        SensitivityMetadata(3, ("restricted",), ("internal",), ("asset/parent",)),
    )
    assert result.effective_level == "restricted"
    assert transport.calls[0][1].endswith("/catalog/assets/asset%2Fchild/sensitivity")


def test_quality_public_operations_validate_and_preserve_payloads() -> None:
    transport = FakeTransport(
        [
            {"asset": {"asset_id": "orders", "version": "v1"}},
            {"run_id": "run-1", "gate_passed": True},
            {"items": [{"run_id": "run-1"}]},
            {"latest_status": "passed"},
        ]
    )
    client = Ronin(transport=transport)
    assert client.get_quality_contract("workspace/1", "orders", "v1")["asset"]
    assert client.run_quality("workspace/1", {"run_id": "run-1"})["gate_passed"] is True
    assert client.list_quality_runs("workspace/1", "orders", "v1")[0]["run_id"] == "run-1"
    assert client.get_quality_state("workspace/1", "orders", "v1")["latest_status"] == "passed"


def test_streaming_health_is_parsed_and_stream_id_is_encoded() -> None:
    transport = FakeTransport(
        [
            {
                "stream_id": "events/main",
                "checkpoint_digest": "a" * 64,
                "partitions": 2,
                "lag": {"0": 0, "1": 3},
                "total_lag": 3,
                "healthy": False,
            }
        ]
    )
    health = Ronin(transport=transport).streaming_health("workspace", "events/main")
    assert health.total_lag == 3
    assert health.lag["1"] == 3
    assert transport.calls[0][1] == "/v1/workspaces/workspace/streams/events%2Fmain/health"


def test_semantic_models_and_query_are_validated() -> None:
    transport = FakeTransport(
        [
            {"items": [{"id": "sales", "name": "Sales"}]},
            {"columns": [{"name": "revenue", "type": "double"}], "rows": [[12.5]]},
        ]
    )
    client = Ronin(transport=transport)
    assert client.list_semantic_models("w", "p")[0]["id"] == "sales"
    result = client.query_semantic("w", "p", {"model_id": "sales", "measures": ["revenue"]})
    assert result.columns[0].name == "revenue"
    assert result.rows == ((12.5,),)


def test_semantic_dashboards_are_listed_and_executed() -> None:
    transport = FakeTransport(
        [
            {"items": [{"id": "sales-dashboard", "name": "Sales", "tiles": []}]},
            {"dashboard_id": "sales-dashboard", "tiles": []},
        ]
    )
    client = Ronin(transport=transport)
    assert client.list_semantic_dashboards("w", "p")[0]["id"] == "sales-dashboard"
    result = client.execute_semantic_dashboard("w", "p", "sales-dashboard")
    assert result["tiles"] == []
    assert transport.calls[1][1].endswith("/semantic/dashboards/sales-dashboard/execute")


def test_client_retries_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = HTTPTransport(
        "https://example.test",
        max_retries=2,
        backoff_seconds=0.25,
    )
    opener = _FlakyOpener(failures=2)
    object.__setattr__(transport, "_opener", opener)
    sleeps: list[float] = []
    monkeypatch.setattr("pyronin.time.sleep", sleeps.append)

    assert transport.request("GET", "/health") == {"ok": True}
    assert opener.calls == 3
    assert sleeps == [0.25, 0.5]


def test_platform_plugins_parses_surface_metadata() -> None:
    transport = FakeTransport(
        [
            {
                "items": [
                    {
                        "id": "com.example.data",
                        "version": "1.0.0",
                        "state": "ready",
                        "error": None,
                    }
                ],
                "surfaces": [
                    {
                        "id": "com.example.data.preview",
                        "plugin_id": "com.example.data",
                        "namespace": "data",
                        "command": "preview",
                        "operation_id": "data.preview.v1",
                        "capability": "data:read",
                        "permission": "data:read",
                        "transport": "http",
                        "api_version": "1.0",
                        "path": "/v1/data/preview",
                        "method": "POST",
                    }
                ],
                "cli": [
                    {
                        "id": "com.example.data.preview",
                        "namespace": "data",
                        "command": "preview",
                        "operation_id": "data.preview.v1",
                        "options": ["limit"],
                    }
                ],
                "client_operations": [
                    {
                        "id": "com.example.data.preview",
                        "operation_id": "data.preview.v1",
                        "transport": "http",
                        "path": "/v1/data/preview",
                        "method": "POST",
                    }
                ],
            }
        ]
    )
    platform = Ronin(transport=transport).platform_plugins()
    assert platform.items[0].state == "ready"
    assert platform.surfaces[0].operation_id == "data.preview.v1"
    assert platform.cli[0].options == ("limit",)
    assert platform.client_operations[0].method == "POST"
    assert transport.calls[0][0:2] == ("GET", "/v1/platform/plugins")


def test_connector_capabilities_and_preview_are_public_sdk_contracts() -> None:
    transport = FakeTransport(
        [
            {"http-json": {"read": True}},
            {
                "schema": "ronin.ingestion-preview/v1",
                "plan": {"mode": "snapshot"},
                "rows": [{"id": "1"}],
            },
        ]
    )
    client = Ronin(transport=transport)
    assert client.platform_connectors()["http-json"]["read"] is True
    result = client.preview_connector({"id": "p", "mode": "snapshot"})
    assert result["rows"] == [{"id": "1"}]
    assert transport.calls[1][0:2] == ("POST", "/v1/platform/connectors/preview")


def test_connector_plan_and_checkpoint_health_are_public_sdk_contracts() -> None:
    transport = FakeTransport(
        [
            {"plan": {"mode": "snapshot"}, "checkpoint": {"present": False}},
            {"identity": "sync-1", "present": False},
        ]
    )
    client = Ronin(transport=transport)
    assert client.plan_connector({"id": "sync-1"})["plan"]["mode"] == "snapshot"
    assert client.connector_checkpoint_health("sync-1")["present"] is False
    assert transport.calls[0][1] == "/v1/platform/connectors/plan"
    assert transport.calls[1][2] == {"checkpoint_identity": "sync-1"}


def test_plugin_client_invokes_advertised_operation() -> None:
    transport = FakeTransport(
        [
            {
                "items": [],
                "surfaces": [
                    {
                        "id": "com.example.data.preview",
                        "plugin_id": "com.example.data",
                        "namespace": "data",
                        "command": "preview",
                        "operation_id": "data.preview.v1",
                        "capability": "data:read",
                        "permission": "data:read",
                        "transport": "http",
                        "api_version": "1.0",
                        "path": "/v1/data/preview",
                        "method": "POST",
                    }
                ],
            },
            {"ok": True},
        ]
    )
    result = (
        Ronin(transport=transport).plugin("data").invoke("data.preview.v1", payload={"limit": 10})
    )
    assert result == {"ok": True}
    assert transport.calls[1][0:3] == ("POST", "/v1/data/preview", {"limit": 10})


def test_plugin_client_expands_and_escapes_path_parameters() -> None:
    transport = FakeTransport(
        [
            {
                "items": [],
                "surfaces": [
                    {
                        "id": "com.example.run",
                        "plugin_id": "com.example",
                        "namespace": "example",
                        "command": "run",
                        "operation_id": "example.run.v1",
                        "capability": "example.run",
                        "permission": "example:execute",
                        "transport": "http",
                        "api_version": "1.0",
                        "path": "/v1/example/labs/{lab_id}/runs",
                        "method": "POST",
                    }
                ],
            },
            {"id": "run-1"},
        ]
    )
    result = (
        Ronin(transport=transport)
        .plugin("example")
        .invoke("example.run.v1", path_params={"lab_id": "lab/a"}, payload={"x": 1})
    )
    assert result == {"id": "run-1"}
    assert transport.calls[1][1] == "/v1/example/labs/lab%2Fa/runs"


def test_platform_plugins_rejects_malformed_surface_metadata() -> None:
    client = Ronin(transport=FakeTransport([{"items": [], "surfaces": [{"id": "bad"}]}]))
    with pytest.raises(ProtocolError, match="surface fields"):
        client.platform_plugins()


def test_unsafe_submission_without_idempotency_is_not_retried() -> None:
    transport = HTTPTransport("https://example.test", max_retries=3, backoff_seconds=0)
    opener = _FlakyOpener(failures=3)
    object.__setattr__(transport, "_opener", opener)

    with pytest.raises(TransportError):
        transport.request("POST", "/v1/jobs", payload={"project": "demo"})
    assert opener.calls == 1


def test_list_jobs_and_validation() -> None:
    transport = FakeTransport(
        [
            {
                "items": [{"id": "job-1", "state": "failed", "failure_code": "x"}],
                "next_cursor": "next-1",
            }
        ]
    )
    client = Ronin(transport=transport)
    page = client.list_jobs(project="demo", state=JobState.FAILED, limit=25, cursor="cursor-0")
    assert page.items[0].failure_code == "x"
    assert page.next_cursor == "next-1"
    assert transport.calls[0][4] == {
        "limit": "25",
        "project": "demo",
        "state": "failed",
        "cursor": "cursor-0",
    }
    with pytest.raises(ValueError):
        Ronin()
    with pytest.raises(ValueError):
        Ronin("https://example.test", transport=transport)
    with pytest.raises(ValueError):
        client.submit(project="", target="x")
    with pytest.raises(ValueError):
        client.list_jobs(project="")
    with pytest.raises(ValueError):
        client.list_jobs(limit=0)
    with pytest.raises(ValueError):
        client.list_jobs(cursor=" ")
    with pytest.raises(ValueError):
        client.get_events("job", limit=0)
    with pytest.raises(ValueError):
        client.get_events("job", since=" ")


def test_execute_sql_parses_result_and_sends_bounded_request() -> None:
    transport = FakeTransport(
        [
            {
                "columns": [{"name": "total", "type": "BIGINT"}],
                "rows": [[7]],
            }
        ]
    )
    client = Ronin(transport=transport)
    result = client.execute_sql(
        project="demo",
        sql="SELECT sum(value) AS total FROM events",
        parameters=("events",),
        max_rows=25,
    )
    assert result.columns[0].name == "total"
    assert result.rows == ((7,),)
    assert transport.calls[0][0:3] == (
        "POST",
        "/v1/sql",
        {
            "project": "demo",
            "sql": "SELECT sum(value) AS total FROM events",
            "parameters": ["events"],
            "max_rows": 25,
        },
    )
    with pytest.raises(ValueError):
        client.execute_sql(project="demo", sql="SELECT 1", max_rows=0)
    with pytest.raises(ValueError):
        client.execute_sql(project="demo", sql="SELECT 1", profile="unknown")


@pytest.mark.parametrize(
    "payload",
    [
        {"columns": [{"name": "value", "type": "INTEGER", "extra": True}], "rows": []},
        {"columns": [{"name": "value", "type": "INTEGER"}], "rows": [[1, 2]]},
        {"columns": "not-an-array", "rows": []},
    ],
)
def test_invalid_sql_results_fail_closed(payload: object) -> None:
    with pytest.raises(ProtocolError):
        Ronin(transport=FakeTransport([payload])).execute_sql(project="demo", sql="SELECT 1")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"id": "", "state": "queued"},
        {"id": "job", "state": "unknown"},
        {"id": "job", "state": "failed", "failure_code": 7},
    ],
)
def test_invalid_job_payloads_fail_closed(payload: dict[str, object]) -> None:
    with pytest.raises(ProtocolError):
        Ronin(transport=FakeTransport([payload])).get_job("job")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"items": [], "next_cursor": None, "extra": True},
        {"items": {}, "next_cursor": None},
        {"items": [], "next_cursor": ""},
    ],
)
def test_invalid_job_page_payloads_fail_closed(payload: object) -> None:
    with pytest.raises(ProtocolError):
        Ronin(transport=FakeTransport([payload])).list_jobs()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"items": [], "next_since": "cursor", "extra": True},
        {"items": {}, "next_since": "cursor"},
        {"items": [], "next_since": ""},
        {
            "items": [
                {
                    "sequence": 0,
                    "attempt_id": "attempt-1",
                    "attempt_sequence": -1,
                    "kind": "started",
                    "message": "x",
                    "occurred_at": "2026-09-07T11:00:00.000000Z",
                }
            ],
            "next_since": "cursor",
        },
    ],
)
def test_invalid_event_page_payloads_fail_closed(payload: object) -> None:
    with pytest.raises(ProtocolError):
        Ronin(transport=FakeTransport([payload])).get_events("job")


def test_backfill_lifecycle_uses_authenticated_control_plane_paths() -> None:
    transport = FakeTransport(
        [{"id": "bf-1"}, {"id": "bf-1"}, {"id": "bf-1", "state": "cancelled"}]
    )
    client = Ronin(transport=transport)
    assert (
        client.create_backfill(
            "ws/a", "bf-1", "schedule-1", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"
        )["id"]
        == "bf-1"
    )
    assert client.get_backfill("ws/a", "bf-1")["id"] == "bf-1"
    assert client.cancel_backfill("ws/a", "bf-1")["state"] == "cancelled"
    assert [call[:3] for call in transport.calls] == [
        (
            "POST",
            "/v1/workspaces/ws%2Fa/backfills",
            {
                "id": "bf-1",
                "schedule_id": "schedule-1",
                "start_at": "2026-01-01T00:00:00Z",
                "end_at": "2026-01-02T00:00:00Z",
            },
        ),
        ("GET", "/v1/workspaces/ws%2Fa/backfills/bf-1", None),
        ("POST", "/v1/workspaces/ws%2Fa/backfills/bf-1/cancel", {}),
    ]


def test_preview_schedule_next_runs_uses_bounded_query() -> None:
    transport = FakeTransport([{"items": ["2026-01-01T00:00:00.000000Z"]}])
    client = Ronin(transport=transport)
    assert client.preview_schedule_next_runs(
        "ws/a", "schedule-1", "2026-01-01T00:00:00.000000Z", count=3
    ) == ("2026-01-01T00:00:00.000000Z",)
    assert transport.calls == [
        (
            "GET",
            "/v1/workspaces/ws%2Fa/schedules/schedule-1/next-runs",
            None,
            None,
            {"after": "2026-01-01T00:00:00.000000Z", "count": "3"},
        )
    ]


def test_schedule_history_uses_bounded_query() -> None:
    transport = FakeTransport([{"items": [{"scheduled_for": "2026-01-01T00:00:00.000000Z"}]}])
    client = Ronin(transport=transport)
    assert client.list_schedule_history("ws/a", "schedule-1", limit=4)[0]["scheduled_for"]
    assert transport.calls == [
        (
            "GET",
            "/v1/workspaces/ws%2Fa/schedules/schedule-1/history",
            None,
            None,
            {"limit": "4"},
        )
    ]


def test_event_trigger_list_and_replace_use_scheduler_paths() -> None:
    transport = FakeTransport(
        [
            {"items": [{"id": "trigger-1"}]},
            {"id": "trigger-1", "enabled": False},
        ]
    )
    client = Ronin(transport=transport)
    assert client.list_event_triggers("ws/a", limit=2)[0]["id"] == "trigger-1"
    assert (
        client.replace_event_trigger("ws/a", "trigger-1", {"id": "trigger-1", "enabled": False})[
            "enabled"
        ]
        is False
    )
    assert [call[:3] for call in transport.calls] == [
        (
            "GET",
            "/v1/workspaces/ws%2Fa/event-triggers",
            None,
        ),
        (
            "PUT",
            "/v1/workspaces/ws%2Fa/event-triggers/trigger-1",
            {"id": "trigger-1", "enabled": False},
        ),
    ]


def test_scheduler_event_ingestion_uses_authenticated_path() -> None:
    transport = FakeTransport([{"event_id": "event-1", "deliveries": ["pending"]}])
    result = Ronin(transport=transport).ingest_scheduler_event(
        "ws/a",
        "event-1",
        "dataset.updated",
        "a" * 64,
        "2026-01-01T00:00:00.000000Z",
        source_ref="source-1",
    )
    assert result["event_id"] == "event-1"
    assert transport.calls[0][0:3] == (
        "POST",
        "/v1/workspaces/ws%2Fa/events",
        {
            "event_id": "event-1",
            "event_type": "dataset.updated",
            "payload_digest": "a" * 64,
            "occurred_at": "2026-01-01T00:00:00.000000Z",
            "source_ref": "source-1",
        },
    )


def test_pending_event_deliveries_use_bounded_query() -> None:
    transport = FakeTransport([{"items": [{"event_id": "event-1", "state": "pending"}]}])
    result = Ronin(transport=transport).list_pending_event_deliveries("ws/a", limit=3)
    assert result[0]["event_id"] == "event-1"
    assert transport.calls[0][1] == "/v1/workspaces/ws%2Fa/event-deliveries"
    assert transport.calls[0][4] == {"limit": "3"}


def test_workflow_run_read_uses_scheduler_path() -> None:
    transport = FakeTransport([{"id": "run-1", "tasks": []}])
    result = Ronin(transport=transport).get_workflow_run("ws/a", "run-1")
    assert result["id"] == "run-1"
    assert transport.calls[0] == (
        "GET",
        "/v1/workspaces/ws%2Fa/workflow-runs/run-1",
        None,
        None,
        None,
    )


def test_workflow_run_cancellation_uses_scheduler_path() -> None:
    transport = FakeTransport([{"workflow_run_id": "run-1", "cancelled_jobs": 2}])
    result = Ronin(transport=transport).cancel_workflow_run("ws/a", "run-1")
    assert result["cancelled_jobs"] == 2
    assert transport.calls[0] == (
        "POST",
        "/v1/workspaces/ws%2Fa/workflow-runs/run-1/cancel",
        {},
        None,
        None,
    )


def test_workflow_run_creation_uses_idempotent_scheduler_path() -> None:
    transport = FakeTransport([{"id": "run-1", "state": "pending"}])
    result = Ronin(transport=transport).create_workflow_run(
        "ws/a",
        "workflow-1",
        {"kind": "manual", "source_ref": "operator"},
        idempotency_key="request-1",
    )
    assert result["id"] == "run-1"
    assert transport.calls[0][0:3] == (
        "POST",
        "/v1/workspaces/ws%2Fa/workflows/workflow-1/runs",
        {
            "trigger": {"kind": "manual", "source_ref": "operator"},
            "idempotency_key": "request-1",
        },
    )


def test_schedule_crud_uses_scheduler_paths() -> None:
    transport = FakeTransport(
        [
            {"items": [{"id": "schedule-1"}]},
            {"id": "schedule-1"},
            {"id": "schedule-1", "enabled": False},
        ]
    )
    client = Ronin(transport=transport)
    assert client.list_schedules("ws/a")[0]["id"] == "schedule-1"
    assert client.get_schedule("ws/a", "schedule-1")["id"] == "schedule-1"
    assert (
        client.replace_schedule("ws/a", "schedule-1", {"id": "schedule-1", "enabled": False})[
            "enabled"
        ]
        is False
    )
    assert [call[:3] for call in transport.calls] == [
        ("GET", "/v1/workspaces/ws%2Fa/schedules", None),
        ("GET", "/v1/workspaces/ws%2Fa/schedules/schedule-1", None),
        (
            "PUT",
            "/v1/workspaces/ws%2Fa/schedules/schedule-1",
            {"id": "schedule-1", "enabled": False},
        ),
    ]


def test_backfill_preview_uses_non_mutating_scheduler_path() -> None:
    transport = FakeTransport([{"items": ["2026-01-01T00:00:00.000000Z"]}])
    result = Ronin(transport=transport).preview_backfill(
        "ws/a",
        "schedule-1",
        "2026-01-01T00:00:00.000000Z",
        "2026-01-01T01:00:00.000000Z",
        max_runs=2,
    )
    assert result == ("2026-01-01T00:00:00.000000Z",)
    assert transport.calls[0][0:3] == (
        "POST",
        "/v1/workspaces/ws%2Fa/backfills/preview",
        {
            "schedule_id": "schedule-1",
            "start_at": "2026-01-01T00:00:00.000000Z",
            "end_at": "2026-01-01T01:00:00.000000Z",
            "max_runs": 2,
        },
    )


def test_workflow_list_uses_scheduler_path() -> None:
    transport = FakeTransport([{"items": [{"id": "workflow-1"}]}])
    result = Ronin(transport=transport).list_workflows("ws/a", limit=4)
    assert result[0]["id"] == "workflow-1"
    assert transport.calls[0][1] == "/v1/workspaces/ws%2Fa/workflows"
    assert transport.calls[0][4] == {"limit": "4"}


def test_notebook_lifecycle_uses_project_scoped_paths() -> None:
    transport = FakeTransport(
        [
            {"items": [{"id": "nb-1"}]},
            {"id": "nb-1"},
            {"id": "nb-1", "revision": 1},
            {"id": "nb-1", "revision": 2},
            {"id": "nb-1", "revision": 3},
            {"deleted": True},
        ]
    )
    client = Ronin(transport=transport)
    assert client.list_notebooks("ws", "project")[0]["id"] == "nb-1"
    assert client.get_notebook("ws", "project", "nb-1")["id"] == "nb-1"
    assert client.create_notebook("ws", "project", {"id": "nb-1"})["revision"] == 1
    assert client.save_notebook("ws", "project", "nb-1", {"expected_revision": 1})["revision"] == 2
    assert client.archive_notebook("ws", "project", "nb-1", 2)["revision"] == 3
    assert client.delete_notebook("ws", "project", "nb-1", 3)["deleted"] is True
    assert transport.calls[-1][3] == {"If-Match": "3"}
