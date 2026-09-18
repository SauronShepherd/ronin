# ADR V01-012: Neutral runner boundary

**Status:** accepted for design; conformance implementation pending  
**Scope:** local runner-broker boundary and a future process/remote runner  
**Date:** 2026-09-18

## Decision

Ronin will use a versioned JSON protocol over HTTP for a process boundary between
the control/worker plane and a runner. The protocol is transport-neutral at the
contract level: HTTP is the first local transport, while a future Unix socket or
other bounded stream transport may carry the same envelopes.

The canonical protocol is provider-neutral and must not contain Docker argv,
cloud IAM syntax, provider SDK objects, Python module paths, pickle payloads or
implementation exception classes. Provider-specific data belongs in explicitly
namespaced adapter extensions and is never required to interpret the core
execution result.

The first protocol version is `ronin/runner/v1`. A peer MUST reject an unknown
required protocol version, unknown required capability, malformed identity,
unbounded body, duplicate request identity or an extension it cannot safely
ignore. Optional extension fields may be ignored only when their names are
explicitly namespaced and the envelope remains semantically complete.

## Core envelopes

Every request and response is a bounded canonical-JSON object with:

- `protocol`: `ronin/runner/v1`;
- `message_type`: one of `capabilities`, `dispatch`, `heartbeat`, `cancel`,
  `result`, or `error`;
- `request_id`: stable idempotency identity;
- `execution_id` and, where applicable, `attempt_id`;
- `capabilities`: only on negotiation responses;
- `payload`: the message-specific object.

`dispatch` carries the prepared cell language/source and bounded execution
metadata. It does not carry an executable command line, mount list, image
selection, network policy, credentials or host authority. `heartbeat` carries
the attempt identity, lease token and monotonic progress state. `cancel` carries
the execution identity and cancellation reason. `result` carries the normalized
outcome, redacted diagnostics, evidence references and resource observations.

Leases and fencing remain owned by the durable worker/storage boundary. A runner
may report a fencing token, but it cannot extend or replace authoritative lease
state. A result with a stale token is rejected by the owner of durable state.

## Semantics

- Dispatch is at-least-once at the transport boundary and exactly-once by
  `(execution_id, attempt_id, request_id)` at the durable owner.
- Retries reuse the same request identity; peers must return the prior terminal
  result or a stable in-progress response rather than execute a duplicate.
- Messages are unary in v1. Streaming logs are represented by bounded evidence
  references and ordered result metadata; live streaming is a later capability,
  not an implicit behavior.
- Cancellation is best effort and idempotent. The terminal result determines
  whether cancellation won the race with completion.
- Backpressure is explicit: a peer returns a normalized capacity error instead
  of accepting an unbounded queue.
- Errors use a stable code, bounded message and retry classification. Raw stack
  traces, secrets and provider response bodies are never protocol fields.

## Capability negotiation

The initial negotiation advertises a sorted set of capability identifiers such
as `execute.python`, `cancel.cooperative`, `evidence.reference.v1` and
`resource.observation.v1`. Required capabilities are listed separately from
optional capabilities. A peer rejects the session if any required capability is
missing; it may continue with a reduced optional set only when the dispatch
semantics remain complete.

## Compatibility and follow-up

This ADR closes the design decision required before a non-Python runner is
considered. It does not claim that a second-language peer exists or that the
current broker is a complete conformance implementation. The follow-up must add
canonical golden fixtures, a schema validator, and one independent non-Python
checker before `#62` can be closed. Existing local Python contracts remain the
source of behavior and must map losslessly when the boundary is introduced.

