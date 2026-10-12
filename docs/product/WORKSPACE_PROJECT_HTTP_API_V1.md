# Workspace and project HTTP API v1

**Status:** implementation contract for the Public v1 control-plane slice tracked by #367.  
**Application service dependency:** #364 (`WorkspaceService` / `ProjectService`).  
**Security composition:** authentication and authorization are injected policy dependencies; concrete OIDC/RBAC composition is intentionally separate.

## Scope

This surface exposes lifecycle operations for workspaces, registered portable project manifests, and workspace-scoped connection metadata. It does not define workspace bootstrap/creation, IAM administration, environment/deployment APIs, or Web Studio.

Workspace creation is deliberately excluded because the current security contract defines workspace-scoped permissions but no global `workspace.create` authority. A bootstrap/control-plane policy must be designed before exposing that mutation.

## Routes

| Method | Path | Permission |
| --- | --- | --- |
| `GET` | `/v1/workspaces` | `workspace.read` per returned workspace |
| `GET` | `/v1/workspaces/{workspace_id}` | `workspace.read` |
| `PATCH` | `/v1/workspaces/{workspace_id}` | `workspace.admin` |
| `POST` | `/v1/workspaces/{workspace_id}/archive` | `workspace.admin` |
| `GET` | `/v1/workspaces/{workspace_id}/projects` | `project.read` |
| `POST` | `/v1/workspaces/{workspace_id}/projects` | `project.write` |
| `GET` | `/v1/workspaces/{workspace_id}/projects/{project_id}` | `project.read` |
| `PUT` | `/v1/workspaces/{workspace_id}/projects/{project_id}` | `project.write` |
| `DELETE` | `/v1/workspaces/{workspace_id}/projects/{project_id}` | `project.write` |
| `GET` | `/v1/workspaces/{workspace_id}/connections` | `workspace.read` |
| `POST` | `/v1/workspaces/{workspace_id}/connections` | `workspace.write` |
| `GET` | `/v1/workspaces/{workspace_id}/connections/{connection_id}` | `workspace.read` |
| `PUT` | `/v1/workspaces/{workspace_id}/connections/{connection_id}` | `workspace.write` |
| `DELETE` | `/v1/workspaces/{workspace_id}/connections/{connection_id}` | `workspace.write` |

The workspace list is authorization-filtered before pagination so workspace identifiers without `workspace.read` are not returned.

## Payloads

Workspace responses contain `id`, `name`, `description`, and `state`. Workspace `PATCH` accepts exactly `name` and `description`; archival is a separate idempotent action and accepts no body.

Project request/response bodies are the canonical `ronin.project/v1` `ProjectManifest` representation. Project replacement requires the manifest project id to equal the id in the request path. Portable manifests cannot embed repository authentication references.

Connection request/response bodies contain `id`, `name`, `connector_id`, non-secret string `options`, and opaque `secret_refs` using `secret://` URIs. Plaintext credentials and credential-bearing option keys are rejected by the canonical `ConnectionDefinition` contract. Connection replacement requires the definition id to match the request path; deletion is idempotent at the application boundary and returns the deleted id.

List routes accept only `limit` and `cursor`, with a maximum page size of 100. Cursors are opaque transport values and callers must not interpret their contents.

## Transport and failure policy

All routes require an injected `ControlPlaneAuthenticator`. Authorization uses an injected `ControlPlaneAuthorizer` over the existing `Actor`, `PolicyRequirement`, and `PolicyDecision` contracts. The HTTP layer does not import SQLite/PostgreSQL adapters or instantiate the current RBAC store directly.

Mutation authorization occurs before request-body parsing. If authentication/authorization dependencies explicitly report unavailability, requests fail closed with `503` and the application mutation is not invoked.

Request bodies are bounded to 1 MiB, require `Content-Length`, reject `Transfer-Encoding`, and use a bounded socket read deadline. Mutation routes reject query parameters unless documented. Stable JSON error families are used for invalid requests, authentication/authorization denial, missing resources, conflicts, timeouts, unsupported methods, and security dependency unavailability.

## Evidence boundary

This document and implementation are source contracts only. Verification is maintained in a separate stacked PR. Concrete OIDC/store-authoritative RBAC/audit integration and exact-candidate CI/release evidence remain separate work; this surface by itself is not Public v1 qualification.
