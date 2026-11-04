# Local Scheduler API — Public v1 contract

This contract describes the scheduler implemented by the `local-composed`
profile. It uses the existing workspace authentication and typed-grant model.
It is a local, single-operator product surface; it does not promise production
availability, multi-user access, or a remote-control compatibility SLA.

## Resource model

- A **workflow** is a versioned pipeline definition that already exists in a
  workspace. This API lists workflows and starts runs; it does not create or
  edit workflow definitions.
- A **schedule** binds a workflow to a cron trigger. The scheduler records
  durable fires and prevents a repeated fire identity from creating duplicate
  runs.
- An **event trigger** binds a workflow to a named event. Event delivery
  history records its outcome and any workflow run created from that delivery.
- A **workflow run** executes one workflow snapshot and retains durable
  workflow/task state.
- A **backfill** requests bounded replay over a schedule interval. Creation
  stores an immutable execution-plan snapshot; cancellation is durable.

## Routes

All routes are workspace-scoped. Requests use the existing authentication and
grant checks. The canonical request and response schemas are in
[`../../api/openapi-v1.json`](../../api/openapi-v1.json).

| Method | Route | Purpose |
|---|---|---|
| GET | `/v1/workspaces/{workspace_id}/workflows` | List workflows available to the scheduler |
| POST | `/v1/workspaces/{workspace_id}/workflows/{workflow_id}/runs` | Start a run from the current workflow snapshot |
| GET | `/v1/workspaces/{workspace_id}/workflow-runs/{run_id}` | Read durable workflow and task state |
| POST | `/v1/workspaces/{workspace_id}/workflow-runs/{run_id}/cancel` | Request idempotent cancellation |
| GET | `/v1/workspaces/{workspace_id}/schedules` | List schedules |
| GET, PUT | `/v1/workspaces/{workspace_id}/schedules/{schedule_id}` | Read or create/update a schedule |
| GET | `/v1/workspaces/{workspace_id}/schedules/{schedule_id}/next-runs` | Preview upcoming cron fires |
| GET | `/v1/workspaces/{workspace_id}/schedules/{schedule_id}/history` | Read durable fire history |
| GET | `/v1/workspaces/{workspace_id}/event-triggers` | List event triggers |
| PUT | `/v1/workspaces/{workspace_id}/event-triggers/{trigger_id}` | Create/update an event trigger |
| GET | `/v1/workspaces/{workspace_id}/event-deliveries` | Read event delivery history, including linked runs |
| POST | `/v1/workspaces/{workspace_id}/backfills/preview` | Preview a bounded backfill plan |
| POST | `/v1/workspaces/{workspace_id}/backfills` | Create a backfill and persist its plan snapshot |
| GET | `/v1/workspaces/{workspace_id}/backfills/{backfill_id}` | Read backfill state and plan |
| POST | `/v1/workspaces/{workspace_id}/backfills/{backfill_id}/cancel` | Cancel a backfill |

Event ingestion is performed by the configured local event source; the public
HTTP API currently exposes trigger configuration and delivery inspection but
does not define a generic public event-ingestion endpoint. Backfills can be
read by ID, but there is no collection-list route for backfills in this API
version.

## Runtime and persistence

`local-composed` owns the scheduler daemon lifecycle alongside the HTTP server.
The daemon acquires a durable leadership lease, polls schedule/event/backfill
work, retries transient provider errors, and releases its lease at shutdown.
SQLite and PostgreSQL scheduler stores provide durable schedule, event,
delivery, fire, and backfill state. The service has lifecycle and recovery
coverage in the local qualification suites.

This does not establish a supported high-availability deployment, a production
multi-replica contract, or an SLA. The public release remains single-operator;
multi-user Ronin Pro capabilities and in-product GenAI are outside this
contract. External coding-agent skills remain independently packaged
instructions and are not invoked by Ronin.

## Invariants

1. A run captures its workflow snapshot at creation time; later edits do not
   change that run.
2. Run creation accepts an idempotency key and returns the existing run for a
   repeated key with the same canonical request.
3. Cancellation is monotonic and idempotent. It cannot turn a terminal success
   into a different terminal state.
4. Events and delivery records are durable, ordered, workspace-scoped, and
   retain their linked workflow run IDs when a run is created.
5. A repeated schedule-fire identity creates at most one run.
6. A created backfill retains the bounded plan snapshot used for execution;
   later schedule edits do not rewrite that plan.
7. Provider names, deployment locators, and secret values are not part of
   workflow identity or public run payloads.

## Qualification boundary

The current implementation and API schema are exercised by unit/integration
tests and by the real `local-composed` live qualification against isolated
SQLite, PostgreSQL, Redpanda, Chromium, and Docker-worker services. Passing
those tests is diagnostic evidence for the tested worktree; it does not by
itself qualify a clean Public v1 release candidate or every scheduler/provider
combination.
