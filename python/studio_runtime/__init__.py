"""Runtime-only plugin discovery and bootstrap helpers."""

from __future__ import annotations

import hashlib
import importlib.metadata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from studio_core.audit import AuditActor, AuditEvent, AuditEventId, AuditResource
from studio_core.plugins import (
    CompositionPlan,
    PluginLoadError,
    PluginManager,
    PluginRecord,
    PluginState,
    RouteContribution,
)
from studio_core.workspaces import WorkspaceId
from studio_runtime.events import DispatchResult, PluginEventDispatcher
from studio_runtime.lockfile import PluginLock, PluginLockError
from studio_runtime.settings import (
    PluginSettingsError,
    PluginSettingsRegistry,
    PluginSettingsSpec,
    SecretReference,
)


def _distribution_digest(distribution: importlib.metadata.Distribution) -> str | None:
    try:
        files = distribution.files
    except OSError:
        return None
    if files is None:
        return None
    digest = hashlib.sha256()
    found = False
    for relative in sorted(files, key=str):
        path = Path(str(distribution.locate_file(relative)))
        try:
            if not path.is_file():
                continue
            content = path.read_bytes()
        except OSError:
            continue
        found = True
        digest.update(str(relative).encode("utf-8"))
        digest.update(content)
    return digest.hexdigest() if found else None


class PluginAuditSink:
    """Adapt sanitized plugin invocation records to Ronin's audit port."""

    def __init__(
        self,
        append: Callable[[WorkspaceId, AuditEvent], AuditEvent],
        workspace_id: WorkspaceId,
    ) -> None:
        self._append = append
        self._workspace_id = workspace_id

    def __call__(self, invocation: dict[str, object]) -> None:
        occurred_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        plugin_id = str(invocation.get("plugin_id", "unknown"))
        path = str(invocation.get("path", "unknown"))
        identifier = hashlib.sha256(f"{occurred_at}|{plugin_id}|{path}".encode()).hexdigest()
        metadata = tuple(
            (key, str(value))
            for key, value in sorted(invocation.items())
            if key not in {"event", "plugin_id", "path"}
        )
        event = AuditEvent(
            id=AuditEventId(f"plugin-{identifier}"),
            occurred_at=occurred_at,
            actor=AuditActor("local", "ronin-plugin-runtime"),
            action=f"plugin.route.{invocation.get('result', 'unknown')}",
            resource=AuditResource("plugin", f"{plugin_id}:{path}"),
            outcome="succeeded" if invocation.get("result") == "success" else "failed",
            metadata=metadata,
        )
        self._append(self._workspace_id, event)


def discover_plugins(
    *,
    group: str = "ronin.plugins.v1",
    include_builtins: bool = False,
    ignore_load_errors: bool = False,
) -> tuple[PluginRecord, ...]:
    """Discover installed entry points without putting packaging in domain code.

    ``ignore_load_errors`` is intended for safe-mode/bootstrap inventory. Normal
    startup remains fail-closed and raises :class:`PluginLoadError` so a broken
    explicitly selected plugin cannot be silently hidden.
    """

    discovered: list[PluginRecord] = []
    entry_points = importlib.metadata.entry_points()
    selected = (
        entry_points.select(group=group)
        if hasattr(entry_points, "select")
        else cast(Any, entry_points).get(group, ())
    )
    for entry_point in sorted(selected, key=lambda item: item.name):
        try:
            factory = entry_point.load()
            plugin = factory()
            manifest = plugin.manifest
            manifest.validate()
            distribution = getattr(entry_point, "dist", None)
            discovered.append(
                PluginRecord(
                    manifest,
                    plugin,
                    str(entry_point),
                    distribution=distribution.metadata["Name"] if distribution else None,
                    distribution_version=distribution.version if distribution else None,
                    artifact_hash=_distribution_digest(distribution) if distribution else None,
                )
            )
        except Exception as exc:
            if ignore_load_errors:
                continue
            raise PluginLoadError(f"could not load plugin entry point {entry_point.name}") from exc
    if include_builtins:
        from studio_plugin_observability import LoggingPlugin, MonitoringPlugin
        from studio_plugin_workspaces import factory as workspaces_factory
        from studio_synthetic_data.plugin import factory as synthetic_data_studio_factory

        builtin_factories = (
            ("builtin:workspaces", workspaces_factory),
            ("builtin:logging", LoggingPlugin),
            ("builtin:monitoring", MonitoringPlugin),
            ("builtin:synthetic-data-studio", synthetic_data_studio_factory),
        )
        known_ids = {record.manifest.id for record in discovered}
        for source, factory in builtin_factories:
            plugin = factory()
            plugin.manifest.validate()
            if plugin.manifest.id not in known_ids:
                discovered.append(PluginRecord(plugin.manifest, plugin, source))
        discovered.sort(key=lambda record: record.manifest.id)
    return tuple(discovered)


@dataclass
class PluginHost:
    """Operational facade used by local/server composition roots."""

    manager: PluginManager
    plan: CompositionPlan | None = None
    states: tuple[PluginRecord, ...] = ()
    audit: Callable[[dict[str, object]], None] | None = None
    settings_registry: PluginSettingsRegistry | None = None

    @classmethod
    def discover(
        cls,
        *,
        host_version: str = "1.0.0",
        plugin_api: str = "1.0",
        services: Mapping[str, object] | None = None,
        settings_registry: PluginSettingsRegistry | None = None,
    ) -> PluginHost:
        manager = PluginManager(host_version=host_version, plugin_api=plugin_api)
        records = discover_plugins(include_builtins=True)
        settings = None
        if settings_registry is not None:
            settings = {
                record.manifest.id: settings_registry.get(record.manifest.id)
                for record in records
                if record.manifest.id in settings_registry.plugin_ids
            }
        return cls(
            manager,
            manager.compose(records, services=services, settings=settings),
            settings_registry=settings_registry,
        )

    def start(self) -> tuple[PluginRecord, ...]:
        if self.plan is None:
            raise PluginLoadError("plugin host has no composition plan")
        self.states = self.manager.start(self.plan)
        return self.states

    def stop(self) -> None:
        if self.plan is not None and self.states:
            self.manager.stop(self.plan)
            self.states = tuple(
                PluginRecord(
                    record.manifest,
                    record.plugin,
                    record.source,
                    PluginState.STOPPED,
                    record.error,
                    record.distribution,
                    record.distribution_version,
                    record.artifact_hash,
                )
                for record in self.states
            )

    def diagnostics(self) -> tuple[dict[str, str | None], ...]:
        records = self.states if self.states else (self.plan.records if self.plan else ())
        return tuple(
            {
                "id": record.manifest.id,
                "version": record.manifest.version,
                "edition": record.manifest.edition,
                "state": record.state.value,
                "error": record.error,
            }
            for record in records
        )

    def contribution_diagnostics(self) -> dict[str, object]:
        """Return stable host-facing composition surface diagnostics."""
        if self.plan is None:
            return {
                "capabilities": {},
                "permissions": {},
                "routes": [],
                "jobs": [],
                "events": [],
                "migrations": [],
                "ui": [],
                "surfaces": [],
                "cli": [],
                "client_operations": [],
            }
        contributions = self.plan.contributions
        return {
            "capabilities": contributions.capabilities,
            "permissions": contributions.permissions,
            "routes": [
                {
                    "path": item.path,
                    "method": item.method.upper(),
                    "plugin_id": item.plugin_id,
                    "permission": item.permission,
                }
                for item in contributions.routes
            ],
            "jobs": [
                {"job_type": item.job_type, "plugin_id": item.plugin_id}
                for item in contributions.job_registry.items
            ],
            "events": [
                {"event_type": item.event_type, "plugin_id": item.plugin_id}
                for item in contributions.event_subscription_registry.items
            ],
            "migrations": [
                {"migration_id": item.migration_id, "plugin_id": item.plugin_id}
                for item in contributions.migration_registry.items
            ],
            "ui": [
                {"plugin_id": item.plugin_id, "manifest": dict(item.manifest)}
                for item in contributions.ui_registry.items
            ],
            "surfaces": [
                {
                    "id": item.id,
                    "plugin_id": item.plugin_id,
                    "namespace": item.namespace,
                    "command": item.command,
                    "operation_id": item.operation_id,
                    "capability": item.capability,
                    "permission": item.permission,
                    "input_schema": dict(item.input_schema),
                    "output_schema": dict(item.output_schema),
                    "options": [
                        {
                            "name": option.name,
                            "schema": dict(option.schema),
                            "required": option.required,
                            "secret": option.secret,
                        }
                        for option in item.options
                    ],
                    "transport": item.transport,
                    "api_version": item.api_version,
                    "path": item.path,
                }
                for item in contributions.surface_registry.items
            ],
            "cli": [
                {
                    "id": item.id,
                    "namespace": item.namespace,
                    "command": item.command,
                    "operation_id": item.operation_id,
                    "options": [option.name for option in item.options],
                }
                for item in contributions.cli_registry.items
            ],
            "client_operations": [
                {
                    "id": item.id,
                    "operation_id": item.operation_id,
                    "transport": item.transport,
                    "path": item.path,
                    "method": item.method.upper(),
                }
                for item in contributions.client_operation_registry.items
            ],
            "settings": {
                "values": self.settings_registry.redacted(),
                "reloadable": self.settings_registry.reloadable(),
            }
            if self.settings_registry is not None
            else {"values": {}, "reloadable": {}},
        }

    def create_lock(self) -> PluginLock:
        if self.plan is None:
            raise PluginLockError("plugin host has no composition plan")
        return PluginLock.from_plan(
            self.plan,
            host_version=self.manager.host_version,
            plugin_api=self.manager.plugin_api,
        )

    def verify_lock(self, lock: PluginLock) -> None:
        if (
            lock.host_version != self.manager.host_version
            or lock.plugin_api != self.manager.plugin_api
        ):
            raise PluginLockError("plugin lock host version or API does not match runtime")
        if self.plan is None:
            raise PluginLockError("plugin host has no composition plan")
        lock.verify_plan(self.plan)

    def resolve_route(
        self, method: str, path: str
    ) -> tuple[RouteContribution, dict[str, str]] | None:
        """Resolve one plugin route without executing its handler."""

        if self.plan is None:
            return None
        actual = tuple(segment for segment in path.strip("/").split("/") if segment)
        for route in self.plan.contributions.routes:
            if route.method != method.upper():
                continue
            expected = tuple(segment for segment in route.path.strip("/").split("/") if segment)
            if len(expected) != len(actual):
                continue
            parameters: dict[str, str] = {}
            matched = True
            for expected_segment, actual_segment in zip(expected, actual, strict=True):
                if expected_segment.startswith("{") and expected_segment.endswith("}"):
                    parameters[expected_segment[1:-1]] = actual_segment
                elif expected_segment != actual_segment:
                    matched = False
                    break
            if matched:
                return route, parameters
        return None

    def invoke_route(
        self,
        method: str,
        path: str,
        *,
        query: str | None = None,
        body: object | None = None,
        idempotency_key: str | None = None,
    ) -> object:
        """Execute a resolved route and emit a sanitized invocation audit event."""

        resolved = self.resolve_route(method, path)
        if resolved is None:
            raise LookupError(f"plugin route not found: {method} {path}")
        route, parameters = resolved
        payload = route.handler(
            **parameters,
            query=query,
            body=body,
            idempotency_key=idempotency_key,
        )
        if self.audit is not None:
            self.audit(
                {
                    "event": "plugin.route.invoked",
                    "plugin_id": route.plugin_id,
                    "method": route.method,
                    "path": route.path,
                    "permission": route.permission,
                    "parameter_names": tuple(sorted(parameters)),
                    "result": "success",
                }
            )
        return payload


__all__ = (
    "PluginAuditSink",
    "PluginHost",
    "PluginLock",
    "PluginLockError",
    "PluginEventDispatcher",
    "DispatchResult",
    "PluginSettingsRegistry",
    "PluginSettingsError",
    "PluginSettingsSpec",
    "SecretReference",
    "discover_plugins",
)
