"""Reproducible plugin composition locks and rollback snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from studio_core.plugins import CompositionPlan, PluginRecord


class PluginLockError(ValueError):
    """The lock is malformed or does not match the requested composition."""


@dataclass(frozen=True, slots=True)
class PluginLockEntry:
    id: str
    version: str
    plugin_api: str
    source: str
    dependencies: tuple[str, ...]
    capabilities: tuple[str, ...]
    permissions: tuple[str, ...]
    job_types: tuple[str, ...]
    event_types: tuple[str, ...]
    migration_ids: tuple[str, ...]
    surface_ids: tuple[str, ...]
    ui_entry: str | None
    config_schema: str | None
    distribution: str | None
    distribution_version: str | None
    artifact_hash: str | None

    @classmethod
    def from_record(cls, record: PluginRecord) -> PluginLockEntry:
        manifest = record.manifest
        return cls(
            id=manifest.id,
            version=manifest.version,
            plugin_api=manifest.plugin_api,
            source=record.source,
            dependencies=tuple(sorted(item.plugin_id for item in manifest.dependencies)),
            capabilities=tuple(sorted(manifest.capabilities)),
            permissions=tuple(sorted(manifest.permissions)),
            job_types=tuple(sorted(manifest.job_types)),
            event_types=tuple(sorted(manifest.event_types)),
            migration_ids=tuple(sorted(manifest.migration_ids)),
            surface_ids=tuple(sorted(manifest.surface_ids)),
            ui_entry=manifest.ui_entry,
            config_schema=manifest.config_schema,
            distribution=record.distribution,
            distribution_version=record.distribution_version,
            artifact_hash=record.artifact_hash,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "plugin_api": self.plugin_api,
            "source": self.source,
            "dependencies": list(self.dependencies),
            "capabilities": list(self.capabilities),
            "permissions": list(self.permissions),
            "job_types": list(self.job_types),
            "event_types": list(self.event_types),
            "migration_ids": list(self.migration_ids),
            "surface_ids": list(self.surface_ids),
            "ui_entry": self.ui_entry,
            "config_schema": self.config_schema,
            "distribution": self.distribution,
            "distribution_version": self.distribution_version,
            "artifact_hash": self.artifact_hash,
        }


@dataclass(frozen=True, slots=True)
class PluginLock:
    schema_version: int
    host_version: str
    plugin_api: str
    plugins: tuple[PluginLockEntry, ...]

    @classmethod
    def from_plan(
        cls, plan: CompositionPlan, *, host_version: str, plugin_api: str
    ) -> PluginLock:
        entries = tuple(
            sorted(
                (PluginLockEntry.from_record(item) for item in plan.records),
                key=lambda item: item.id,
            )
        )
        return cls(1, host_version, plugin_api, entries)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "host_version": self.host_version,
            "plugin_api": self.plugin_api,
            "plugins": [entry.as_dict() for entry in self.plugins],
        }

    def dumps(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n"

    def write(self, path: str) -> None:
        with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(self.dumps())

    @classmethod
    def loads(cls, raw: str) -> PluginLock:
        try:
            payload = json.loads(raw)
            entries = tuple(
                PluginLockEntry(
                    id=item["id"],
                    version=item["version"],
                    plugin_api=item["plugin_api"],
                    source=item["source"],
                    dependencies=tuple(item["dependencies"]),
                    capabilities=tuple(item["capabilities"]),
                    permissions=tuple(item["permissions"]),
                    job_types=tuple(item.get("job_types", ())),
                    event_types=tuple(item.get("event_types", ())),
                    migration_ids=tuple(item.get("migration_ids", ())),
                    surface_ids=tuple(item.get("surface_ids", ())),
                    ui_entry=item.get("ui_entry"),
                    config_schema=item.get("config_schema"),
                    distribution=item.get("distribution"),
                    distribution_version=item.get("distribution_version"),
                    artifact_hash=item.get("artifact_hash"),
                )
                for item in payload["plugins"]
            )
            result = cls(
                schema_version=payload["schema_version"],
                host_version=payload["host_version"],
                plugin_api=payload["plugin_api"],
                plugins=entries,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PluginLockError("invalid plugin lock format") from exc
        result.validate()
        return result

    @classmethod
    def read(cls, path: str) -> PluginLock:
        with Path(path).open(encoding="utf-8") as handle:
            return cls.loads(handle.read())

    def validate(self) -> None:
        if self.schema_version != 1:
            raise PluginLockError(f"unsupported plugin lock schema: {self.schema_version}")
        ids = [entry.id for entry in self.plugins]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise PluginLockError("plugin lock entries must be unique and sorted")
        for entry in self.plugins:
            if entry.dependencies != tuple(sorted(entry.dependencies)):
                raise PluginLockError(f"dependencies are not sorted for {entry.id}")

    def verify_plan(self, plan: CompositionPlan) -> None:
        actual = tuple(
            sorted((PluginLockEntry.from_record(item) for item in plan.records), key=lambda x: x.id)
        )
        if actual != self.plugins:
            raise PluginLockError("composition does not match plugin lock")


__all__ = ("PluginLock", "PluginLockEntry", "PluginLockError")
