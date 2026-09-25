"""HTTP-neutral ontology and Knowledge Graph application boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from studio_core import (
    ActionExecution,
    ActionType,
    GraphQueryExecutor,
    KnowledgeGraph,
    KnowledgeObject,
    KnowledgeObjectRef,
    LocalGraphQueryExecutor,
    OntologyDefinition,
    OntologyId,
    Requirement,
    RqlResult,
    WorkspaceId,
    execute_ontology_action,
    parse_rql,
)


class OntologyStore(Protocol):
    def put(
        self, workspace_id: WorkspaceId, ontology: OntologyDefinition, *, now: object
    ) -> OntologyDefinition: ...

    def get(
        self, workspace_id: WorkspaceId, ontology_id: OntologyId, version: str
    ) -> OntologyDefinition | None: ...

    def list_versions(
        self, workspace_id: WorkspaceId, ontology_id: OntologyId
    ) -> tuple[OntologyDefinition, ...]: ...


class GraphStore(Protocol):
    def get(self, graph_id: str) -> KnowledgeGraph | None: ...

    def get_action_replay(self, idempotency_key: str) -> ActionExecution | None: ...

    def record_action_replay(self, execution: ActionExecution) -> None: ...


class OntologyHTTPAdapter:
    """Bounded application adapter; transport and authorization stay outside."""

    def __init__(
        self,
        ontology_store: OntologyStore,
        graph_store: GraphStore,
        *,
        authorize: Callable[[Requirement], bool] | None = None,
        write: Callable[
            [ActionType, KnowledgeObjectRef, Mapping[str, object]], Mapping[str, object]
        ]
        | None = None,
    ) -> None:
        self._ontology = ontology_store
        self._graphs = graph_store
        self._authorize = authorize
        self._write = write

    def put_schema(
        self, workspace_id: WorkspaceId, ontology: OntologyDefinition, *, now: object
    ) -> OntologyDefinition:
        return self._ontology.put(workspace_id, ontology, now=now)

    def get_schema(
        self, workspace_id: WorkspaceId, ontology_id: OntologyId, version: str
    ) -> OntologyDefinition | None:
        return self._ontology.get(workspace_id, ontology_id, version)

    def list_schema_versions(
        self, workspace_id: WorkspaceId, ontology_id: OntologyId
    ) -> tuple[OntologyDefinition, ...]:
        return self._ontology.list_versions(workspace_id, ontology_id)

    def query(self, graph_id: str, query: str, *, max_limit: int = 1000) -> RqlResult:
        graph = self._graphs.get(graph_id)
        if graph is None:
            raise KeyError(graph_id)
        parsed = parse_rql(query)
        executor: GraphQueryExecutor = LocalGraphQueryExecutor(graph)
        return executor.execute(parsed, max_limit=max_limit)

    def list_objects(
        self, graph_id: str, object_type: str, *, limit: int = 100
    ) -> tuple[KnowledgeObject, ...]:
        graph = self._graphs.get(graph_id)
        if graph is None:
            raise KeyError(graph_id)
        if not 1 <= limit <= 1000:
            raise ValueError("object limit must be between 1 and 1000")
        return graph.objects_of_type(object_type, limit=limit)

    def neighbors(
        self, graph_id: str, ref: KnowledgeObjectRef, *, limit: int = 100
    ) -> tuple[KnowledgeObjectRef, ...]:
        graph = self._graphs.get(graph_id)
        if graph is None:
            raise KeyError(graph_id)
        if not 1 <= limit <= 1000:
            raise ValueError("neighbor limit must be between 1 and 1000")
        return graph.neighbors(ref, limit=limit)

    def execute_action(
        self,
        action: ActionType,
        target: KnowledgeObjectRef,
        inputs: dict[str, object],
        *,
        authorize: Callable[[Requirement], bool],
        write: Callable[
            [ActionType, KnowledgeObjectRef, Mapping[str, object]], Mapping[str, object]
        ],
        idempotency_key: str | None = None,
    ) -> ActionExecution:
        return execute_ontology_action(
            action,
            target,
            inputs,
            authorize=authorize,
            write=write,
            idempotency_key=idempotency_key,
            load_idempotent=(
                self._graphs.get_action_replay if idempotency_key is not None else None
            ),
            record_idempotent=self._graphs.record_action_replay,
        )

    def execute_action_payload(
        self, graph_id: str, payload: dict[str, object]
    ) -> dict[str, object]:
        if self._authorize is None or self._write is None:
            raise RuntimeError("graph action callbacks are not configured")
        action = ActionType.from_payload(payload["action"])
        target_value = payload["target"]
        if not isinstance(target_value, Mapping):
            raise ValueError("graph action target must be an object")
        if set(target_value) != {"object_type", "key"}:
            raise ValueError("graph action target has invalid shape")
        object_type = target_value["object_type"]
        raw_key = target_value["key"]
        if not isinstance(object_type, str) or not object_type.strip():
            raise ValueError("graph action target object_type must be a non-empty string")
        if (
            not isinstance(raw_key, list)
            or not raw_key
            or any(
                not isinstance(item, (list, tuple))
                or len(item) != 2
                or not isinstance(item[0], str)
                or not item[0].strip()
                or not isinstance(item[1], (str, int, float, bool))
                for item in raw_key
            )
        ):
            raise ValueError("graph action target key must be a non-empty key pair array")
        target = KnowledgeObjectRef(object_type, tuple((item[0], item[1]) for item in raw_key))
        inputs = payload["inputs"]
        if not isinstance(inputs, dict):
            raise ValueError("graph action inputs must be an object")
        key = payload.get("idempotency_key")
        if key is not None and (not isinstance(key, str) or not key.strip()):
            raise ValueError("graph action idempotency_key must be non-empty string or null")
        result = self.execute_action(
            action,
            target,
            inputs,
            authorize=self._authorize,
            write=self._write,
            idempotency_key=key,
        )
        return {
            "action": result.action,
            "target": {
                "object_type": result.target.object_type,
                "key": list(result.target.key),
            },
            "output": dict(result.output),
            "graph_id": graph_id,
        }


__all__ = ("GraphStore", "OntologyHTTPAdapter", "OntologyStore")
