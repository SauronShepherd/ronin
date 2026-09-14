from __future__ import annotations

import http.client
import json
from contextlib import contextmanager
from threading import Thread
from typing import Iterator

from studio_core import (
    ExecutionProfile,
    Project,
    ProjectId,
    ProjectManifest,
    RepositoryBinding,
    RuntimeProfileRef,
    Workspace,
    WorkspaceId,
)
from studio_execution import ProjectService, WorkspaceService
from studio_security import Actor, PolicyDecision, Principal, PrincipalId
from studio_server import (
    ControlPlaneUnavailable,
    WorkspaceProjectHTTPServer,
)

_WS_A = WorkspaceId("workspace-a")
_WS_B = WorkspaceId("workspace-b")
_WS_C = WorkspaceId("workspace-c")
_PROJECT = ProjectId("project-1")
_NOW = "2026-09-14T08:45:00.000000Z"


class _Store:
    def __init__(self) -> None:
        self.workspaces: dict[WorkspaceId, Workspace] = {}
        self.projects: dict[tuple[WorkspaceId, ProjectId], ProjectManifest] = {}
        self.calls: dict[str, int] = {}

    def _called(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def create_workspace(self, workspace, *, now):
        del now
        self._called("create_workspace")
        self.workspaces[workspace.id] = workspace
        return workspace

    def get_workspace(self, workspace_id):
        return self.workspaces.get(workspace_id)

    def list_workspaces(self):
        return tuple(sorted(self.workspaces.values(), key=lambda item: item.id.value))

    def update_workspace(self, workspace, *, now):
        del now
        self._called("update_workspace")
        self.workspaces[workspace.id] = workspace
        return workspace

    def register_project(self, workspace_id, manifest, *, now):
        del now
        self._called("register_project")
        self.projects[(workspace_id, manifest.project.id)] = manifest
        return manifest

    def replace_project(self, workspace_id, manifest, *, now):
        del now
        self._called("replace_project")
        self.projects[(workspace_id, manifest.project.id)] = manifest
        return manifest

    def get_project(self, workspace_id, project_id):
        return self.projects.get((workspace_id, project_id))

    def list_projects(self, workspace_id):
        return tuple(
            manifest
            for (found_workspace, _project_id), manifest in sorted(
                self.projects.items(), key=lambda item: item[0][1].value
            )
            if found_workspace == workspace_id
        )

    def unregister_project(self, workspace_id, project_id):
        self._called("unregister_project")
        return self.projects.pop((workspace_id, project_id), None) is not None


_ACTOR = Actor(
    Principal(
        PrincipalId("principal-test"),
        "user",
        "Test User",
        "https://issuer.example.test",
        "subject-test",
    )
)


class _Authenticator:
    def authenticate(self, authorization):
        return _ACTOR if authorization == "Bearer good" else None


class _Authorizer:
    def __init__(self, allowed: set[tuple[str, str]] | None = None) -> None:
        self.allowed = allowed
        self.requirements = []
        self.unavailable = False

    def authorize(self, actor, requirement):
        assert actor == _ACTOR
        self.requirements.append(requirement)
        if self.unavailable:
            raise ControlPlaneUnavailable("dependency unavailable")
        allowed = self.allowed is None or (str(requirement.workspace_id), requirement.permission) in self.allowed
        return PolicyDecision(allowed, "allowed" if allowed else "denied", ("admin",) if allowed else ())


def _manifest(name: str = "Project") -> ProjectManifest:
    return ProjectManifest.from_project(
        Project(
            _PROJECT,
            name,
            (
                RepositoryBinding(
                    "code",
                    "https://git.example.test/team/project.git",
                    role="primary",
                ),
            ),
            ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
        )
    )


@contextmanager
def _server(
    store: _Store,
    authorizer: _Authorizer,
) -> Iterator[tuple[str, int]]:
    server = WorkspaceProjectHTTPServer(
        ("127.0.0.1", 0),
        WorkspaceService(store),
        ProjectService(store),
        authenticator=_Authenticator(),
        authorizer=authorizer,
        request_timeout_seconds=1.0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _request(
    address: tuple[str, int],
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    authorization: str | None = "Bearer good",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    conn = http.client.HTTPConnection(*address, timeout=3)
    request_headers = dict(headers or {})
    if authorization is not None:
        request_headers["Authorization"] = authorization
    if body is not None and "Content-Length" not in request_headers:
        request_headers["Content-Length"] = str(len(body))
    conn.request(method, path, body=body, headers=request_headers)
    response = conn.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    status = response.status
    conn.close()
    return status, payload


def _json_body(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def test_authentication_and_denial_are_stable_json() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    authorizer = _Authorizer(set())
    with _server(store, authorizer) as address:
        status, payload = _request(address, "GET", f"/v1/workspaces/{_WS_A}", authorization=None)
        assert status == 401
        assert payload["error"]["code"] == "unauthorized"

        status, payload = _request(address, "GET", f"/v1/workspaces/{_WS_A}")
        assert status == 403
        assert payload["error"]["code"] == "forbidden"
        assert authorizer.requirements[-1].permission == "workspace.read"


def test_workspace_list_filters_before_pagination() -> None:
    store = _Store()
    for workspace_id in (_WS_A, _WS_B, _WS_C):
        store.workspaces[workspace_id] = Workspace(workspace_id, workspace_id.value)
    authorizer = _Authorizer(
        {
            (str(_WS_A), "workspace.read"),
            (str(_WS_C), "workspace.read"),
        }
    )
    with _server(store, authorizer) as address:
        status, first = _request(address, "GET", "/v1/workspaces?limit=1")
        assert status == 200
        assert [item["id"] for item in first["items"]] == [str(_WS_A)]
        assert first["next_cursor"] is not None
        assert str(_WS_B) not in json.dumps(first)

        status, second = _request(
            address,
            "GET",
            f"/v1/workspaces?limit=1&cursor={first['next_cursor']}",
        )
        assert status == 200
        assert [item["id"] for item in second["items"]] == [str(_WS_C)]
        assert second["next_cursor"] is None


def test_workspace_update_archive_and_method_mapping() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A", "before")
    authorizer = _Authorizer()
    with _server(store, authorizer) as address:
        status, updated = _request(
            address,
            "PATCH",
            f"/v1/workspaces/{_WS_A}",
            body=_json_body({"name": "Renamed", "description": "after"}),
        )
        assert status == 200
        assert updated["name"] == "Renamed"
        assert authorizer.requirements[-1].permission == "workspace.admin"

        status, archived = _request(address, "POST", f"/v1/workspaces/{_WS_A}/archive")
        assert status == 200
        assert archived["state"] == "archived"

        status, payload = _request(address, "POST", f"/v1/workspaces/{_WS_A}")
        assert status == 405
        assert payload["error"]["code"] == "method_not_allowed"

        status, payload = _request(
            address,
            "PATCH",
            f"/v1/workspaces/{_WS_A}",
            body=_json_body({"name": "Blocked", "description": None}),
        )
        assert status == 409
        assert payload["error"]["code"] == "conflict"


def test_project_http_lifecycle_uses_canonical_manifest_and_resource_ref() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    authorizer = _Authorizer()
    original = _manifest()
    changed = _manifest("Changed")
    with _server(store, authorizer) as address:
        status, created = _request(
            address,
            "POST",
            f"/v1/workspaces/{_WS_A}/projects",
            body=original.to_json().encode("utf-8"),
        )
        assert status == 201
        assert created == original.to_data()
        assert store.calls["register_project"] == 1
        assert authorizer.requirements[-1].permission == "project.write"

        status, found = _request(
            address,
            "GET",
            f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}",
        )
        assert status == 200
        assert found == original.to_data()
        assert authorizer.requirements[-1].resource_ref == str(_PROJECT)

        status, listed = _request(address, "GET", f"/v1/workspaces/{_WS_A}/projects?limit=1")
        assert status == 200
        assert listed["items"] == [original.to_data()]

        status, replaced = _request(
            address,
            "PUT",
            f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}",
            body=changed.to_json().encode("utf-8"),
        )
        assert status == 200
        assert replaced == changed.to_data()
        assert store.calls["replace_project"] == 1

        status, deleted = _request(
            address,
            "DELETE",
            f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}",
        )
        assert status == 200
        assert deleted == {"unregistered": True, "project_id": str(_PROJECT)}
        assert store.calls["unregister_project"] == 1

        status, payload = _request(
            address,
            "GET",
            f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}",
        )
        assert status == 404
        assert payload["error"]["code"] == "not_found"


def test_denied_and_unavailable_mutations_fail_before_body_parse_or_store_write() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    denied = _Authorizer(set())
    with _server(store, denied) as address:
        status, payload = _request(
            address,
            "POST",
            f"/v1/workspaces/{_WS_A}/projects",
            body=b"{not-json",
        )
        assert status == 403
        assert payload["error"]["code"] == "forbidden"
        assert store.calls.get("register_project", 0) == 0

    unavailable = _Authorizer()
    unavailable.unavailable = True
    with _server(store, unavailable) as address:
        status, payload = _request(
            address,
            "PATCH",
            f"/v1/workspaces/{_WS_A}",
            body=b"{not-json",
        )
        assert status == 503
        assert payload["error"]["code"] == "authorization_unavailable"
        assert store.calls.get("update_workspace", 0) == 0


def test_invalid_shapes_query_cursor_and_project_id_mismatch_are_400() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    authorizer = _Authorizer()
    with _server(store, authorizer) as address:
        cases = [
            ("GET", "/v1/workspaces?limit=101", None),
            ("GET", "/v1/workspaces?cursor=invalid", None),
            (
                "PATCH",
                f"/v1/workspaces/{_WS_A}?unexpected=1",
                _json_body({"name": "A", "description": None}),
            ),
            (
                "PATCH",
                f"/v1/workspaces/{_WS_A}",
                _json_body({"name": "A", "description": None, "extra": True}),
            ),
        ]
        for method, path, body in cases:
            status, payload = _request(address, method, path, body=body)
            assert status == 400
            assert payload["error"]["code"] == "invalid_request"

        other = ProjectManifest.from_project(
            Project(
                ProjectId("project-other"),
                "Other",
                (RepositoryBinding("code", "https://git.example.test/other.git", role="primary"),),
                ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
            )
        )
        store.projects[(_WS_A, _PROJECT)] = _manifest()
        status, payload = _request(
            address,
            "PUT",
            f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}",
            body=other.to_json().encode("utf-8"),
        )
        assert status == 400
        assert payload["error"]["code"] == "invalid_request"
        assert store.calls.get("replace_project", 0) == 0


def test_missing_and_archived_project_mutations_map_to_stable_errors() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    authorizer = _Authorizer()
    with _server(store, authorizer) as address:
        status, payload = _request(
            address,
            "PUT",
            f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}",
            body=_manifest().to_json().encode("utf-8"),
        )
        assert status == 404
        assert payload["error"]["code"] == "not_found"

        store.workspaces[_WS_A] = Workspace(_WS_A, "A", state="archived")
        status, payload = _request(
            address,
            "POST",
            f"/v1/workspaces/{_WS_A}/projects",
            body=_manifest().to_json().encode("utf-8"),
        )
        assert status == 409
        assert payload["error"]["code"] == "conflict"
        assert store.calls.get("register_project", 0) == 0
