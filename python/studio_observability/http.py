"""HTTP-neutral adapter for durable alert rules and state evaluation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from studio_orchestrator import Instant

from .alerts import AlertTransition, evaluate_alert
from .contracts import AlertRule


class _Payload(Protocol):
    def to_payload(self) -> dict[str, object]: ...


class AlertHTTPStore(Protocol):
    def list_alert_rules(self) -> tuple[AlertRule, ...]: ...

    def list_alert_instances(self, *, limit: int = 100) -> tuple[_Payload, ...]: ...

    def acknowledge_alert(
        self, rule_id: str, fingerprint: str, *, acknowledged_at: Instant | str
    ) -> _Payload | None: ...


class AlertHTTPAdapter:
    """Expose bounded alert operations without embedding transport concerns."""

    def __init__(self, store: AlertHTTPStore | Callable[[str], AlertHTTPStore]) -> None:
        self._store = store

    def _store_for_workspace(self, workspace_id: str | None) -> AlertHTTPStore:
        if callable(self._store):
            if workspace_id is None:
                raise ValueError("workspace-scoped alert storage requires a workspace ID")
            return self._store(workspace_id)
        return self._store

    def list_rules(self, *, workspace_id: str | None = None) -> dict[str, object]:
        store = self._store_for_workspace(workspace_id)
        return {"items": [rule.to_payload() for rule in store.list_alert_rules()]}

    def list_instances(
        self, *, limit: int = 100, workspace_id: str | None = None
    ) -> dict[str, object]:
        store = self._store_for_workspace(workspace_id)
        return {
            "items": [instance.to_payload() for instance in store.list_alert_instances(limit=limit)]
        }

    def evaluate(
        self,
        body: object,
        *,
        now: Instant | str,
        workspace_id: str | None = None,
    ) -> dict[str, object]:
        if not isinstance(body, dict) or set(body) != {"rule_id"}:
            raise ValueError("alert evaluation body must contain only rule_id")
        rule_id = body["rule_id"]
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError("alert rule_id must be a non-empty string")
        store = self._store_for_workspace(workspace_id)
        rule = next((item for item in store.list_alert_rules() if item.id == rule_id), None)
        if rule is None:
            raise KeyError(f"alert rule not found: {rule_id}")
        transition: AlertTransition = evaluate_alert(store, rule, now=now)  # type: ignore[arg-type]
        return {
            "rule_id": rule.id,
            "changed": transition.changed,
            "metric": None if transition.metric is None else transition.metric.to_payload(),
            "state": None if transition.current is None else transition.current.to_payload(),
        }

    def acknowledge(
        self,
        body: object,
        *,
        now: Instant | str,
        workspace_id: str | None = None,
    ) -> dict[str, object]:
        if not isinstance(body, dict) or set(body) != {"rule_id", "fingerprint"}:
            raise ValueError("alert acknowledgement body must contain rule_id and fingerprint")
        rule_id = body["rule_id"]
        fingerprint = body["fingerprint"]
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError("alert rule_id must be a non-empty string")
        if not isinstance(fingerprint, str) or not fingerprint.strip():
            raise ValueError("alert fingerprint must be a non-empty string")
        store = self._store_for_workspace(workspace_id)
        instance = store.acknowledge_alert(rule_id, fingerprint, acknowledged_at=now)
        if instance is None:
            raise KeyError("alert instance not found")
        return {"rule_id": rule_id, "state": instance.to_payload()}


__all__ = ("AlertHTTPAdapter", "AlertHTTPStore")
