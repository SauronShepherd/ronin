# IR identity and stable instance anchors

Ronin node identity must remain deterministic across editing, serialization, import, replay and graph canonicalization. It must also distinguish two nodes that are semantically identical.

## Identity contract

A node identifier is derived from two inputs:

1. the node's canonical semantic payload: operator/version, parameters, logical inputs and logical outputs; and
2. a stable `instance_key` that identifies the authored/imported instance independently of those semantics.

Labels, canvas coordinates, insertion order and graph traversal order are not identity inputs. Renaming a node therefore does not change its identity. Changing semantic behavior does change its identity while retaining the same instance key, which provides continuity evidence across revisions.

The `instance_key` is persisted with the node in canonical IR. Deserialization recomputes `NodeId` from the semantic payload plus the persisted key and rejects mismatches. An IR document therefore cannot silently carry an identifier that disagrees with its identity evidence.

## Authoring and import boundaries

`studio_core.InstanceAnchor` represents the stable provenance supplied by an authoring or import boundary. It has two bounded origins:

- `authoring`: an editor/document-owned stable slot or element reference;
- `import`: a stable source-system element/reference chosen by an importer.

The pure core deterministically hashes `(boundary, reference)` into an instance key. `allocate_instance_keys()` rejects duplicate anchors in the same allocation batch. It does not create random IDs, read clocks, inspect files, consult a database or maintain a process-global counter.

The boundary that owns the source document is responsible for persisting the anchor. Examples include a stable canvas element ID, notebook cell ID, source AST element ID or external object ID. Mutable labels, line numbers that shift on unrelated edits, list position and current graph topology are poor anchors unless the source format itself guarantees their stability.

## Symmetric graphs

Two structurally identical nodes in a symmetric graph cannot be assigned stable distinct identities from graph structure alone. Any topology-only algorithm must either treat automorphic nodes as indistinguishable or introduce an arbitrary traversal/order tie-breaker that changes under unrelated edits.

Ronin therefore requires external stable instance provenance at authoring/import time. Canonical graph ordering consumes identity; it never invents identity. Identical nodes with distinct stable anchors receive distinct IDs, and reversing node/edge insertion order does not alter the canonical serialized graph.

## Reuse boundary

The design adapts a proven idea from `sdp-studio`: persisted document node IDs are allocated before lowering and carried through IR/source provenance. Ronin does not copy `sdp-studio`'s ULID allocator into `studio_core` because that allocator intentionally depends on wall-clock time and OS randomness.

A future editor/storage layer may use an opaque random identifier implementation for newly authored elements if desired, but that side effect belongs outside the pure core. Once allocated, the stable anchor must be persisted and supplied explicitly to the deterministic domain contract.
