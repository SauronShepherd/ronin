# Local Scheduler API — Public v1 contract

This contract exposes the local workflow scheduler without exposing provider
or deployment-specific implementation details. It is intended for the local
Web Studio and local automation clients; it is not a production SLA or a
remote-control compatibility promise.

## Resource model

- A **workflow** is an immutable, versioned pipeline definition in a workspace.
- A **schedule** binds a workflow to a local trigger such as cron or an event.
- A **workflow run** is one durable execution of one workflow snapshot.
- A **task run** is the durable execution record for one pipeline node.
- Events and evidence are append-only observations; they do not mutate the
  workflow definition.

## Minimum routes

All routes are workspace-scoped and use the existing authentication and grant
model.

| Method | Route | Purpose |
|---|---|---|
| GET | `/v1/workflows` | List workflow definitions with cursor pagination |
| POST | `/v1/workflows/{workflow_id}/runs` | Create one run from the current workflow snapshot |
| GET | `/v1/workflow-runs/{run_id}` | Read durable workflow and task state |
| POST | `/v1/workflow-runs/{run_id}/cancel` | Request idempotent cancellation |
| GET | `/v1/workflow-runs/{run_id}/events` | Read ordered event pages |
| GET | `/v1/schedules` | List local schedules |
| POST | `/v1/schedules/{schedule_id}/trigger` | Fire one schedule deterministically |

## Invariants

1. A run captures the workflow snapshot at creation time; later edits do not
   alter that run.
2. Run creation accepts an idempotency key and returns the existing run for a
   repeated key with the same canonical request.
3. Cancellation is monotonic and idempotent. It cannot turn a terminal success
   into a different terminal state.
4. Events are returned in durable sequence order and are scoped to the caller's
   workspace and workflow run.
5. Schedule triggering creates at most one run for the same schedule fire
   identity.
6. Provider names, deployment locators and secret values are not part of the
   workflow identity or public run payload.

## Initial implementation boundary

The first implementation targets the existing SQLite/local scheduler services
and typed-grant HTTP server. PostgreSQL, remote runners, production deployment
and provider-specific compatibility remain out of scope for this contract.

The contract is deliberately small so Web Studio can build against stable
local semantics while scheduler internals continue to evolve behind the
provider-neutral boundary.
