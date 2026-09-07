# JobStore concurrency boundary

Ronin's canonical `JobStore` remains a synchronous, storage-neutral protocol. SQLite, in-memory, future database adapters and their transaction/fencing behavior stay behind that protocol; asyncio, HTTP frameworks and worker-loop concerns do not become canonical domain semantics.

## Rule

Blocking `JobStore` and artifact-store operations must never execute directly on an asyncio event-loop thread.

Async server/worker composition must place whole synchronous store operations behind a bounded offload boundary. For v0.1 the reference JobStore boundary is `studio_storage.BoundedAsyncJobStore`, which uses a dedicated thread pool and preserves the wrapped `JobStore` call as the transaction/fencing unit.

`studio_execution.DurableExecutionService` is the shared HTTP-neutral application-composition surface over that facade. Submit/status/cancel and worker reclaim/claim/heartbeat/write calls all enter through the same bounded async store; the service adds no SQLite, HTTP framework, Docker, engine, cloud or provider semantics. `studio_server` and `studio_worker` both depend on this shared layer, and worker code is forbidden by the executable architecture gate from importing `studio_server`.

## Bounded admission and backpressure

`BoundedAsyncJobStore(max_workers=N, max_in_flight=M)` has two independent bounds:

- `max_workers` limits concurrently executing synchronous store calls.
- `max_in_flight` limits running plus executor-queued store calls.

When all `max_in_flight` slots are occupied, the wrapper rejects new work immediately with `StorageBackpressureError`. Callers must translate that provider-neutral pressure signal at their own boundary: HTTP may return a bounded service-unavailable response; a worker loop may defer claim/reclaim work until its next scheduled iteration. Callers must not spin, create unbounded retry tasks, or bypass the wrapper by calling the synchronous store directly.

Cancellation of an awaiting coroutine does not cancel a synchronous operation that may already be mutating durable state. The capacity slot remains reserved until the underlying call finishes. This preserves the concurrency bound and avoids pretending that a Python future cancellation rolled back a SQLite transaction.

## Responsiveness requirements

Server submit/status paths and worker claim/heartbeat/reclaim paths must use the bounded wrapper when they run on asyncio. A slow or contended durable operation must not prevent unrelated coroutine scheduling, cancellation handling or heartbeat timers from making progress.

The shared execution service qualifies this structural requirement with deterministic contention tests, and the real SQLite/local-artifact integration qualification proves unrelated heartbeat/artifact progress through the real adapters. This is still not the final v0.1 HTTP latency qualification; issue #125 remains open until the supported HTTP runtime entry points are benchmarked against the published request budgets and the final worker entry points are qualified against production lease settings.

The wrapper does not weaken SQLite FULL durability settings, lease fencing, idempotency, event sequencing, atomicity or conformance semantics. The same `JobStore` contract suite remains authoritative for the underlying synchronous adapters.

## Worker maintenance order

One worker poll performs expired-lease reclamation before attempting one new claim. These remain separate `JobStore` operations, preserving the already-qualified transaction boundaries. Replacement Attempt identity, lease token, owner, current time and lease duration are supplied by the caller; the composition layer does not introduce clocks, randomness or provider-specific scheduling semantics.

## Artifact stores

The same composition rule applies to blocking artifact-store calls. `studio_storage.BoundedAsyncArtifactStore` provides bounded offload for local artifact persistence and verification; worker code consumes that facade rather than introducing an unbounded executor or leaking filesystem-provider semantics into the shared execution service.
