"""Public plugin contracts and deterministic composition for Ronin.

The module intentionally depends only on the Python standard library and
small typing primitives.  Product plugins may use the resulting context, but
the host never imports a plugin's implementation directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable


class PluginError(RuntimeError):
    """Base error raised while discovering or composing plugins."""


class PluginValidationError(PluginError):
    """A plugin manifest or contribution is invalid."""


class PluginCompatibilityError(PluginError):
    """A plugin cannot run against this host."""


class PluginLoadError(PluginError):
    """An entry point could not be loaded safely."""


class PluginState(StrEnum):
    DISCOVERED = "discovered"
    VALIDATED = "validated"
    REGISTERED = "registered"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PluginDependency:
    plugin_id: str
    version: str = "*"


@dataclass(frozen=True, slots=True)
class PluginManifest:
    id: str
    name: str
    version: str
    plugin_api: str
    host_requires: str = "*"
    edition: str = "community"
    capabilities: tuple[str, ...] = ()
    dependencies: tuple[PluginDependency, ...] = ()
    permissions: tuple[str, ...] = ()
    isolation: str = "in_process"
    critical: bool = False
    job_types: tuple[str, ...] = ()
    event_types: tuple[str, ...] = ()
    migration_ids: tuple[str, ...] = ()
    ui_entry: str | None = None
    config_schema: str | None = None

    def validate(self) -> None:
        if not self.id or self.id != self.id.lower() or "/" in self.id or ".." in self.id:
            raise PluginValidationError(f"invalid plugin id: {self.id!r}")
        if not self.name or not self.version or not self.plugin_api:
            raise PluginValidationError(f"incomplete manifest: {self.id}")
        if self.config_schema is not None and not self.config_schema.strip():
            raise PluginValidationError(f"invalid config schema for {self.id}")
        if self.edition not in {"community", "pro", "third-party"}:
            raise PluginValidationError(f"invalid edition for {self.id}: {self.edition}")
        if self.isolation not in {"in_process", "worker"}:
            raise PluginValidationError(f"invalid isolation for {self.id}: {self.isolation}")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise PluginValidationError(f"duplicate capability in {self.id}")
        if len(set(self.permissions)) != len(self.permissions):
            raise PluginValidationError(f"duplicate permission in {self.id}")
        if any(not item or ":" not in item for item in self.permissions):
            raise PluginValidationError(f"permissions must use namespace:name in {self.id}")
        if len({item.plugin_id for item in self.dependencies}) != len(self.dependencies):
            raise PluginValidationError(f"duplicate dependency in {self.id}")
        for values, label in (
            (self.job_types, "job type"),
            (self.event_types, "event type"),
            (self.migration_ids, "migration id"),
        ):
            if any(not value or value != value.strip() for value in values):
                raise PluginValidationError(f"invalid {label} in {self.id}")
            if len(set(values)) != len(values):
                raise PluginValidationError(f"duplicate {label} in {self.id}")


@dataclass(frozen=True, slots=True)
class PluginContext:
    """Narrow host view handed to a plugin during registration."""

    plugin_id: str
    contributions: ContributionRegistry
    services: Mapping[str, object]
    settings: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))


@runtime_checkable
class RoninPlugin(Protocol):
    manifest: PluginManifest

    def register(self, context: PluginContext) -> None: ...

    def startup(self) -> None: ...

    def shutdown(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PluginRecord:
    manifest: PluginManifest
    plugin: RoninPlugin
    source: str
    state: PluginState = PluginState.DISCOVERED
    error: str | None = None
    distribution: str | None = None
    distribution_version: str | None = None
    artifact_hash: str | None = None


@dataclass(frozen=True, slots=True)
class RouteContribution:
    method: str
    path: str
    plugin_id: str
    handler: Any
    permission: str


@dataclass(frozen=True, slots=True)
class JobContribution:
    job_type: str
    plugin_id: str
    handler: Any


@dataclass(frozen=True, slots=True)
class EventSubscription:
    event_type: str
    plugin_id: str
    handler: Any


@dataclass(frozen=True, slots=True)
class MigrationContribution:
    migration_id: str
    plugin_id: str


@dataclass(frozen=True, slots=True)
class UiContribution:
    plugin_id: str
    manifest: Mapping[str, Any]


class _FrozenRegistry:
    """Small common lifecycle primitive for composition registries."""

    def __init__(self) -> None:
        self._frozen = False

    def _assert_mutable(self) -> None:
        if self._frozen:
            raise PluginValidationError("plugin registry is frozen")

    def freeze(self) -> None:
        self._frozen = True


class CapabilityRegistry(_FrozenRegistry):
    """Maps each capability to exactly one plugin owner."""

    def __init__(self) -> None:
        super().__init__()
        self._items: dict[str, str] = {}

    def add(self, capability: str, plugin_id: str) -> None:
        self._assert_mutable()
        owner = self._items.get(capability)
        if owner is not None and owner != plugin_id:
            raise PluginValidationError(
                f"capability {capability!r} is already provided by {owner}"
            )
        self._items[capability] = plugin_id

    @property
    def items(self) -> dict[str, str]:
        return dict(self._items)


class PermissionRegistry(_FrozenRegistry):
    """Maps each permission to exactly one plugin owner."""

    def __init__(self) -> None:
        super().__init__()
        self._items: dict[str, str] = {}

    def add(self, permission: str, plugin_id: str) -> None:
        self._assert_mutable()
        owner = self._items.get(permission)
        if owner is not None and owner != plugin_id:
            raise PluginValidationError(
                f"permission {permission!r} is already owned by {owner}"
            )
        self._items[permission] = plugin_id

    def owns(self, permission: str, plugin_id: str) -> bool:
        return self._items.get(permission) == plugin_id

    @property
    def items(self) -> dict[str, str]:
        return dict(self._items)


class RouterRegistry(_FrozenRegistry):
    """Registers unique method/path pairs and their plugin ownership."""

    def __init__(self, permissions: PermissionRegistry) -> None:
        super().__init__()
        self._permissions = permissions
        self._items: list[RouteContribution] = []

    def add(
        self,
        method: str,
        path: str,
        plugin_id: str,
        handler: Any,
        *,
        permission: str,
    ) -> None:
        self._assert_mutable()
        if not self._permissions.owns(permission, plugin_id):
            raise PluginValidationError(
                f"route permission {permission!r} is not declared by {plugin_id}"
            )
        key = (method.upper(), path)
        if any((item.method, item.path) == key for item in self._items):
            raise PluginValidationError(f"route collision: {key[0]} {key[1]}")
        self._items.append(RouteContribution(key[0], key[1], plugin_id, handler, permission))

    @property
    def items(self) -> tuple[RouteContribution, ...]:
        return tuple(self._items)


class JobRegistry(_FrozenRegistry):
    def __init__(self) -> None:
        super().__init__()
        self._items: dict[str, JobContribution] = {}

    def add(self, job_type: str, plugin_id: str, handler: Any) -> None:
        self._assert_mutable()
        if job_type in self._items:
            raise PluginValidationError(f"job type collision: {job_type}")
        self._items[job_type] = JobContribution(job_type, plugin_id, handler)

    @property
    def items(self) -> tuple[JobContribution, ...]:
        return tuple(self._items[key] for key in sorted(self._items))


class EventSubscriptionRegistry(_FrozenRegistry):
    def __init__(self) -> None:
        super().__init__()
        self._items: list[EventSubscription] = []

    def add(self, event_type: str, plugin_id: str, handler: Any) -> None:
        self._assert_mutable()
        key = (event_type, plugin_id, id(handler))
        if any((item.event_type, item.plugin_id, id(item.handler)) == key for item in self._items):
            raise PluginValidationError(f"event subscription collision: {event_type}")
        self._items.append(EventSubscription(event_type, plugin_id, handler))

    @property
    def items(self) -> tuple[EventSubscription, ...]:
        return tuple(sorted(self._items, key=lambda item: (item.event_type, item.plugin_id)))


class MigrationRegistry(_FrozenRegistry):
    def __init__(self) -> None:
        super().__init__()
        self._items: dict[str, MigrationContribution] = {}

    def add(self, migration_id: str, plugin_id: str) -> None:
        self._assert_mutable()
        if migration_id in self._items:
            raise PluginValidationError(f"migration collision: {migration_id}")
        self._items[migration_id] = MigrationContribution(migration_id, plugin_id)

    @property
    def items(self) -> tuple[MigrationContribution, ...]:
        return tuple(self._items[key] for key in sorted(self._items))


class UiContributionRegistry(_FrozenRegistry):
    def __init__(self) -> None:
        super().__init__()
        self._items: dict[str, UiContribution] = {}

    def add(self, plugin_id: str, manifest: Mapping[str, Any]) -> None:
        self._assert_mutable()
        if plugin_id in self._items:
            raise PluginValidationError(f"UI contribution collision: {plugin_id}")
        self._items[plugin_id] = UiContribution(plugin_id, dict(manifest))

    @property
    def items(self) -> tuple[UiContribution, ...]:
        return tuple(self._items[key] for key in sorted(self._items))


class ContributionRegistry:
    """Registry for host contributions; frozen after bootstrap."""

    def __init__(self) -> None:
        self.capability_registry = CapabilityRegistry()
        self.permission_registry = PermissionRegistry()
        self.router_registry = RouterRegistry(self.permission_registry)
        self.job_registry = JobRegistry()
        self.event_subscription_registry = EventSubscriptionRegistry()
        self.migration_registry = MigrationRegistry()
        self.ui_registry = UiContributionRegistry()

    def _assert_mutable(self) -> None:
        self.capability_registry._assert_mutable()

    def add_capability(self, capability: str, plugin_id: str) -> None:
        self.capability_registry.add(capability, plugin_id)

    def add_permission(self, permission: str, plugin_id: str) -> None:
        self.permission_registry.add(permission, plugin_id)

    def add_route(
        self,
        method: str,
        path: str,
        plugin_id: str,
        handler: Any,
        *,
        permission: str,
    ) -> None:
        self.router_registry.add(method, path, plugin_id, handler, permission=permission)

    def add_job(self, job_type: str, plugin_id: str, handler: Any) -> None:
        self.job_registry.add(job_type, plugin_id, handler)

    def add_event_subscription(self, event_type: str, plugin_id: str, handler: Any) -> None:
        self.event_subscription_registry.add(event_type, plugin_id, handler)

    def add_migration(self, migration_id: str, plugin_id: str) -> None:
        self.migration_registry.add(migration_id, plugin_id)

    def add_ui(self, plugin_id: str, manifest: Mapping[str, Any]) -> None:
        self.ui_registry.add(plugin_id, manifest)

    def validate_manifest(self, manifest: PluginManifest) -> None:
        plugin_id = manifest.id
        jobs = {item.job_type for item in self.job_registry.items if item.plugin_id == plugin_id}
        events = {
            item.event_type
            for item in self.event_subscription_registry.items
            if item.plugin_id == plugin_id
        }
        migrations = {
            item.migration_id
            for item in self.migration_registry.items
            if item.plugin_id == plugin_id
        }
        if not jobs <= set(manifest.job_types):
            raise PluginValidationError(f"undeclared job contribution in {plugin_id}")
        if not events <= set(manifest.event_types):
            raise PluginValidationError(f"undeclared event contribution in {plugin_id}")
        if not migrations <= set(manifest.migration_ids):
            raise PluginValidationError(f"undeclared migration contribution in {plugin_id}")
        if (
            any(item.plugin_id == plugin_id for item in self.ui_registry.items)
            and not manifest.ui_entry
        ):
            raise PluginValidationError(f"UI contribution requires ui_entry in {plugin_id}")

    def freeze(self) -> None:
        self.capability_registry.freeze()
        self.permission_registry.freeze()
        self.router_registry.freeze()
        self.job_registry.freeze()
        self.event_subscription_registry.freeze()
        self.migration_registry.freeze()
        self.ui_registry.freeze()

    @property
    def routes(self) -> tuple[RouteContribution, ...]:
        return self.router_registry.items

    @property
    def routers(self) -> RouterRegistry:
        """Compatibility view for plugin tests and author tooling."""
        return self.router_registry

    @property
    def capabilities(self) -> dict[str, str]:
        return self.capability_registry.items

    @property
    def permissions(self) -> dict[str, str]:
        return self.permission_registry.items


@dataclass(frozen=True, slots=True)
class CompositionPlan:
    records: tuple[PluginRecord, ...]
    contributions: ContributionRegistry


def _satisfies_host(specifier: str, host_version: str) -> bool:
    """Support the small, explicit subset needed by the bootstrap contract."""
    if specifier in {"", "*"}:
        return True
    # PEP 440 is intentionally not reimplemented here.  This conservative
    # check handles the common >=major,<major+1 form and rejects unknown forms.
    parts = [part.strip() for part in specifier.split(",") if part.strip()]
    try:
        host_major = int(host_version.split(".", 1)[0])
    except ValueError as exc:
        raise PluginCompatibilityError(f"invalid host version: {host_version}") from exc
    for part in parts:
        if part.startswith(">=") and int(part[2:].split(".", 1)[0]) > host_major:
            return False
        if part.startswith("<") and int(part[1:].split(".", 1)[0]) <= host_major:
            return False
        if part.startswith("==") and part[2:] != host_version:
            return False
        if not part.startswith((">=", "<", "==")):
            raise PluginCompatibilityError(f"unsupported host requirement: {specifier}")
    return True


class PluginManager:
    """Discover, validate, compose and lifecycle-manage Ronin plugins."""

    def __init__(self, *, host_version: str = "1.0.0", plugin_api: str = "1.0") -> None:
        self.host_version = host_version
        self.plugin_api = plugin_api
        self._records: dict[str, PluginRecord] = {}
        self._started = False

    def compose(
        self,
        plugins: tuple[PluginRecord, ...],
        *,
        services: Mapping[str, object] | None = None,
        settings: Mapping[str, Mapping[str, object]] | None = None,
    ) -> CompositionPlan:
        if self._records:
            raise PluginValidationError("plugins have already been composed")
        for record in plugins:
            manifest = record.manifest
            if manifest.id in self._records:
                raise PluginValidationError(f"duplicate plugin id: {manifest.id}")
            if manifest.plugin_api != self.plugin_api:
                raise PluginCompatibilityError(
                    f"{manifest.id} requires plugin API {manifest.plugin_api}, "
                    f"host has {self.plugin_api}"
                )
            if not _satisfies_host(manifest.host_requires, self.host_version):
                raise PluginCompatibilityError(
                    f"{manifest.id} is incompatible with host {self.host_version}"
                )
            self._records[manifest.id] = record
        graph = {
            item.manifest.id: {dependency.plugin_id for dependency in item.manifest.dependencies}
            for item in plugins
        }
        missing = sorted(
            {dependency for deps in graph.values() for dependency in deps} - set(graph)
        )
        if missing:
            raise PluginValidationError(f"missing plugin dependencies: {', '.join(missing)}")
        order: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(plugin_id: str) -> None:
            if plugin_id in visiting:
                raise PluginValidationError("plugin dependency cycle")
            if plugin_id in visited:
                return
            visiting.add(plugin_id)
            for dependency in sorted(graph[plugin_id]):
                visit(dependency)
            visiting.remove(plugin_id)
            visited.add(plugin_id)
            order.append(plugin_id)

        for plugin_id in sorted(graph):
            visit(plugin_id)
        registry = ContributionRegistry()
        composed: list[PluginRecord] = []
        for plugin_id in order:
            record = self._records[plugin_id]
            for capability in record.manifest.capabilities:
                registry.add_capability(capability, plugin_id)
            for permission in record.manifest.permissions:
                registry.add_permission(permission, plugin_id)
            record.plugin.register(
                PluginContext(
                    plugin_id,
                    registry,
                    services or {},
                    (settings or {}).get(plugin_id, {}),
                )
            )
            registry.validate_manifest(record.manifest)
            composed.append(
                PluginRecord(
                    record.manifest,
                    record.plugin,
                    record.source,
                    PluginState.REGISTERED,
                    None,
                    record.distribution,
                    record.distribution_version,
                    record.artifact_hash,
                )
            )
        registry.freeze()
        return CompositionPlan(tuple(composed), registry)

    def start(self, plan: CompositionPlan) -> tuple[PluginRecord, ...]:
        if self._started:
            raise PluginValidationError("plugin manager is already started")
        started: list[PluginRecord] = []
        for record in plan.records:
            try:
                record.plugin.startup()
            except Exception as exc:
                if record.manifest.critical:
                    for previous in reversed(started):
                        try:
                            previous.plugin.shutdown()
                        except Exception:  # noqa: S112
                            continue
                    self._started = False
                    raise PluginLoadError(
                        f"critical plugin failed to start: {record.manifest.id}"
                    ) from exc
                started.append(
                    PluginRecord(
                        record.manifest,
                        record.plugin,
                        record.source,
                        PluginState.DEGRADED,
                        str(exc),
                        record.distribution,
                        record.distribution_version,
                        record.artifact_hash,
                    )
                )
            else:
                started.append(
                    PluginRecord(
                        record.manifest,
                        record.plugin,
                        record.source,
                        PluginState.READY,
                        None,
                        record.distribution,
                        record.distribution_version,
                        record.artifact_hash,
                    )
                )
        self._started = True
        return tuple(started)

    def stop(self, plan: CompositionPlan) -> None:
        for record in reversed(plan.records):
            record.plugin.shutdown()
        self._started = False


__all__ = (
    "CompositionPlan",
    "CapabilityRegistry",
    "ContributionRegistry",
    "EventSubscription",
    "EventSubscriptionRegistry",
    "JobContribution",
    "JobRegistry",
    "MigrationContribution",
    "MigrationRegistry",
    "PluginCompatibilityError",
    "PluginContext",
    "PluginDependency",
    "PluginError",
    "PluginLoadError",
    "PluginManager",
    "PluginManifest",
    "PluginRecord",
    "PluginState",
    "PluginValidationError",
    "PermissionRegistry",
    "RouteContribution",
    "RouterRegistry",
    "UiContribution",
    "UiContributionRegistry",
    "RoninPlugin",
)
