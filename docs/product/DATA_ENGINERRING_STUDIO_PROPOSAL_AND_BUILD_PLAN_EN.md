# Data Enginerring Studio — Proposal and Build Plan

## Product outcome

Provide data engineers with a local-first environment where they can author a
pipeline visually or in code, inspect intermediate data, debug cells, validate
the canonical IR, and choose an execution provider without rewriting the
pipeline. The first-class providers are local preview, Spark Connect, and SDP
Studio.

## Design principles

1. Authored intent is provider-neutral and content-addressed.
2. Every compilation produces deterministic diagnostics and an IR digest.
3. Preview is bounded, reproducible, and safe to run locally.
4. External runtimes are explicit providers behind stable ports.
5. Persistence, permissions, leases, evidence, and lineage belong to Ronin;
   providers must not bypass them.
6. Unsupported features fail closed instead of being silently rewritten.

## Component plan

### Canonical model and compiler

Implement versioned pipeline, node, edge, operator, port, parameter, origin,
and ownership contracts. Derive node and pipeline identities from canonical
content. Validate operator names against the builtin catalog, detect invalid
edges and cycles, and emit stable diagnostic codes.

### Designer and IDE

Serve `data-enginerring-studio.html`, JavaScript, and CSS from Ronin. The graph
canvas and code editor must edit the same pipeline JSON. Runtime selection,
validation, preview, and durable submission must use the same IR. IDE sessions
persist cells, prepared source, outputs, diagnostics, breakpoints, and state.

### Runtime providers

The local provider executes fixtures with row and schema bounds. The Spark
Connect provider creates a remote Spark session lazily, executes bounded SQL,
normalizes rows, and records endpoint evidence. The SDP provider imports the
project losslessly and delegates validation/compilation to the installed SDP
Studio implementation.

### Persistence and execution

Store revisions with optimistic concurrency, compilation reports in SQLite,
and outbox events transactionally. Plan durable runs with project, revision,
IR digest, runtime, parameters, idempotency key, and request digest. Execute
through the Ronin worker bridge, fence stale leases, and persist immutable
evidence and lineage.

### HTTP and security

Register plugin routes through the host contribution registry. Map plugin
permissions in the control plane, authenticate every API call, and serve UI
assets with path traversal protection. Browser code is never an authorization
boundary.

## Delivery phases

1. Contracts, manifest, operator catalog, and architecture gates.
2. Compiler, local preview, and deterministic diagnostics.
3. Revision, compilation, outbox, evidence, lineage, and durable execution.
4. Spark Connect and SDP Studio adapters with qualification runners.
5. HTTP routes, same-origin static serving, designer, and IDE.
6. Browser E2E, external runtime E2E, operations runbook, release checklist,
   and English documentation.

## Acceptance matrix

| Area | Evidence |
|---|---|
| IR/compiler | Unit tests and deterministic diagnostics |
| Preview | Fixture execution and bounded result tests |
| Spark Connect | Real Spark Connect `select 1` smoke and evidence artifact |
| SDP Studio | Official `sdpstudio validate` against imported project |
| Persistence | Revision, SQLite compilation, outbox, and fencing tests |
| HTTP | Real control-plane route integration test |
| UI | Browser Validate, Preview, and Submit against Ronin HTTP |
| Operations | English runbook and release checklist |

## Release rule

Release is complete only when mandatory gates pass with real external runtime
evidence. A missing external provider is reported as
`implementation-ready / external-validation-pending`, never as operational
success.
