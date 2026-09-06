# JobStore concurrency boundary

Ronin's canonical `JobStore` remains a synchronous, storage-neutral protocol. SQLite, in-memory, future database adapters and their transaction/fencing behavior stay behind that protocol; asyncio, FastAPI and worker-loop concerns do not become canonical domain semantics.

## Rule

Blocking `JobStore` and artifact-store operations must never execute directly on an asyncio event-loop thread.

Async server/worker composition must place whole synchronous store operations behind a bounded offload boundary. For v0.1 the reference boundary is `studio_storage.BoundedAsyncJobStore`, which uses a dedicated thread pool and preserves the wrapped `JobStore` call as the transaction/fencing unit.

## Bounded admission and backpressure

`BoundedAsyncJobStore(max_workers=N, max_in_flight=M)` has two independent bounds:

- `max_workers` limits concurrently executing synchronous store calls.
- `max_in_flight` limits running plus executor-queued store calls.

When all `max_in_flight` slots are occupied, the wrapper rejects new work immediately with `StorageBackpressureError`. Callers must translate that provider-neutral pressure signal at their own boundary: HTTP may return a bounded service-unavailable response; a worker loop may defer claim/reclaim work until its next scheduled iteration. Callers must not spin, create unbounded retry tasks, or bypass the wrapper by calling the synchronous store directly.

Cancellation of an awaiting coroutine does not cancel a synchronous operation that may already be mutating durable state. The capacity slot remains reserved until the underlying call finishes. This preserves the concurrency bound and avoids pretending that a Python future cancellation rolled back a SQLite transaction.

## Responsiveness requirements

Server submit/status paths and worker claim/heartbeat/reclaim paths must use the bounded wrapper when they run on asyncio. A slow or contended durable operation must not prevent unrelated coroutine scheduling, cancellation handling or heartbeat timers from making progress.

The wrapper does not weaken SQLite durability settings, lease fencing, idempotency, event sequencing, atomicity or conformance semantics. The same `JobStore` contract suite remains authoritative for the underlying synchronous adapters.

## Artifact stores

The same composition rule applies to blocking artifact-store calls. The current slice exposes the `JobStore` wrapper only; server/worker composition must not introduce a second unbounded executor for artifact persistence. A later artifact-facing async facade may share the same bounded execution policy when the first async artifact call site lands.
