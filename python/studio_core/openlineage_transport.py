"""Provider-neutral, bounded OpenLineage transport contract."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from .canonical_json import encode as encode_canonical_json
from .openlineage import JsonValue, _is_valid_iso8601_timestamp

OPENLINEAGE_API_VERSION = "1.0"
SUPPORTED_OPENLINEAGE_SCHEMA_VERSIONS = frozenset({OPENLINEAGE_API_VERSION})
MAX_OPENLINEAGE_EVENT_BYTES = 1_048_576


def _valid_uri(value: object, *, url_only: bool = False) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if any(ord(character) < 0x20 or character.isspace() for character in value):
        return False
    parsed = urlsplit(value)
    if not parsed.scheme:
        return False
    if url_only and parsed.scheme not in {"http", "https"}:
        return False
    if parsed.scheme in {"http", "https"}:
        if not parsed.netloc or not parsed.hostname:
            return False
        try:
            _ = parsed.port
        except ValueError:
            return False
    return True


def _validate_facets(entity: Mapping[str, JsonValue], entity_name: str) -> None:
    if "facets" not in entity:
        return
    facets = entity["facets"]
    if not isinstance(facets, Mapping):
        raise ValueError(f"OpenLineage {entity_name}.facets must be an object")
    for name, facet in facets.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(facet, Mapping):
            raise ValueError(f"OpenLineage {entity_name}.facets entries must be named objects")
        if not _valid_uri(facet.get("_producer")) or not _valid_uri(
            facet.get("_schemaURL"), url_only=True
        ):
            raise ValueError(
                f"OpenLineage {entity_name} facet producer and schemaURL are required URIs"
            )
        if name == "columnLineage":
            fields = facet.get("fields")
            if not isinstance(fields, Mapping) or not fields:
                raise ValueError(
                    "OpenLineage columnLineage facet fields must be a non-empty object"
                )
            for output_field, details in fields.items():
                input_fields = details.get("inputFields") if isinstance(details, Mapping) else None
                if (
                    not isinstance(output_field, str)
                    or not output_field.strip()
                    or not isinstance(input_fields, list)
                    or not input_fields
                ):
                    raise ValueError("OpenLineage columnLineage inputFields are required")
                for input_field in input_fields:
                    if not isinstance(input_field, Mapping):
                        raise ValueError("OpenLineage columnLineage input field is invalid")
                    for key in ("namespace", "name", "field"):
                        value = input_field.get(key)
                        if not isinstance(value, str) or not value.strip():
                            raise ValueError("OpenLineage columnLineage input field is invalid")
        elif name == "lineage":
            inputs = facet.get("inputs")
            fields = facet.get("fields")
            if (not isinstance(inputs, list) or not inputs) and (
                not isinstance(fields, Mapping) or not fields
            ):
                raise ValueError("OpenLineage lineage facet requires inputs or fields")
            if isinstance(inputs, list):
                _validate_lineage_inputs(inputs, "lineage inputs")
            if fields is not None:
                if not isinstance(fields, Mapping):
                    raise ValueError("OpenLineage lineage fields must be an object")
                for field_name, details in fields.items():
                    if not isinstance(field_name, str) or not field_name.strip():
                        raise ValueError("OpenLineage lineage field name is required")
                    if not isinstance(details, Mapping):
                        raise ValueError("OpenLineage lineage field details must be an object")
                    _validate_lineage_inputs(details.get("inputs"), "lineage field inputs")


def _validate_lineage_inputs(value: object, label: str) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError(f"OpenLineage {label} must be a non-empty array")
    for source in value:
        if not isinstance(source, Mapping):
            raise ValueError(f"OpenLineage {label} entries must be objects")
        for key in ("namespace", "name", "type"):
            item = source.get(key)
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"OpenLineage {label} source {key} is required")
        if source["type"] not in {"DATASET", "JOB"}:
            raise ValueError(f"OpenLineage {label} source type is unsupported")
        field_name = source.get("field")
        if field_name is not None and (not isinstance(field_name, str) or not field_name.strip()):
            raise ValueError(f"OpenLineage {label} source field must be non-empty when provided")


def _validate_dataset(value: object, label: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"OpenLineage {label} must be an object")
    namespace = value.get("namespace")
    name = value.get("name")
    if not isinstance(namespace, str) or not namespace.strip():
        raise ValueError(f"OpenLineage {label} namespace is required")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"OpenLineage {label} name is required")
    _validate_facets(value, label)


def _validate_datasets(value: object, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        raise ValueError(f"OpenLineage {field} must be an array")
    for index, dataset in enumerate(value):
        _validate_dataset(dataset, f"{field} dataset at index {index}")


class OpenLineageTransportError(RuntimeError):
    """Raised when an event cannot be delivered after bounded retries."""


class OpenLineageSink(Protocol):
    def publish(self, event: Mapping[str, JsonValue]) -> None: ...


@dataclass(frozen=True, slots=True)
class PublishReceipt:
    event_digest: str
    attempts: int
    deduplicated: bool


def validate_openlineage_event(event: Mapping[str, JsonValue]) -> None:
    """Validate the bounded, supported OpenLineage event subset."""
    if not isinstance(event, Mapping):
        raise ValueError("OpenLineage event must be an object")
    required = {"eventTime", "producer", "schemaURL"}
    if not required <= set(event):
        raise ValueError("OpenLineage event is missing required fields")
    if not _valid_uri(event.get("producer")):
        raise ValueError("OpenLineage producer must be an absolute URI")
    if not _valid_uri(event.get("schemaURL")):
        raise ValueError("OpenLineage schemaURL must be an absolute URI")
    schema_version = event.get("schemaVersion", OPENLINEAGE_API_VERSION)
    if schema_version not in SUPPORTED_OPENLINEAGE_SCHEMA_VERSIONS:
        raise ValueError("OpenLineage schemaVersion is unsupported")
    event_time = event.get("eventTime")
    if not _is_valid_iso8601_timestamp(event_time):
        raise ValueError("OpenLineage eventTime must be a timezone-aware ISO 8601 timestamp")
    if "eventType" in event:
        required_run_fields = {"eventType", "run", "job"}
        if not required_run_fields <= set(event):
            raise ValueError("OpenLineage run event is missing required fields")
        event_type = event.get("eventType")
        if event_type not in {"START", "RUNNING", "COMPLETE", "ABORT", "FAIL", "OTHER"}:
            raise ValueError("OpenLineage event type is unsupported")
        run = event.get("run")
        job = event.get("job")
        if not isinstance(run, Mapping) or not isinstance(job, Mapping):
            raise ValueError("OpenLineage run and job must be objects")
        run_id = run.get("runId")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("OpenLineage run.runId is required")
        namespace = job.get("namespace")
        name = job.get("name")
        if (
            not isinstance(namespace, str)
            or not namespace.strip()
            or not isinstance(name, str)
            or not name.strip()
        ):
            raise ValueError("OpenLineage job namespace and name are required")
        _validate_facets(run, "run")
        _validate_facets(job, "job")
        _validate_datasets(event.get("inputs"), "inputs")
        _validate_datasets(event.get("outputs"), "outputs")
    else:
        if "dataset" not in event:
            raise ValueError("OpenLineage event is missing required fields")
        _validate_dataset(event["dataset"], "dataset")
    try:
        encoded = encode_canonical_json(dict(event))
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise ValueError("OpenLineage event must contain finite JSON values") from exc
    if len(encoded) > MAX_OPENLINEAGE_EVENT_BYTES:
        raise ValueError("OpenLineage event exceeds the 1048576-byte limit")


class OpenLineageTransport:
    """Retrying transport with bounded in-process duplicate suppression."""

    def __init__(
        self,
        sink: OpenLineageSink,
        *,
        max_attempts: int = 3,
        max_deduplication_entries: int = 4096,
    ) -> None:
        if (
            not isinstance(max_attempts, int)
            or isinstance(max_attempts, bool)
            or max_attempts < 1
            or max_attempts > 10
        ):
            raise ValueError("max_attempts must be between 1 and 10")
        if (
            not isinstance(max_deduplication_entries, int)
            or isinstance(max_deduplication_entries, bool)
            or not 1 <= max_deduplication_entries <= 100_000
        ):
            raise ValueError("max_deduplication_entries must be between 1 and 100000")
        self._sink = sink
        self._max_attempts = max_attempts
        self._max_deduplication_entries = max_deduplication_entries
        self._published: OrderedDict[str, None] = OrderedDict()

    @staticmethod
    def _digest(event: Mapping[str, JsonValue]) -> str:
        return hashlib.sha256(encode_canonical_json(dict(event))).hexdigest()

    def publish(self, event: Mapping[str, JsonValue]) -> PublishReceipt:
        validate_openlineage_event(event)
        digest = self._digest(event)
        if digest in self._published:
            self._published.move_to_end(digest)
            return PublishReceipt(digest, 0, True)
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                self._sink.publish(event)
            except Exception as exc:  # noqa: BLE001 - sink failures are retryable transport errors
                last_error = exc
                continue
            self._published[digest] = None
            self._published.move_to_end(digest)
            while len(self._published) > self._max_deduplication_entries:
                self._published.popitem(last=False)
            return PublishReceipt(digest, attempt, False)
        raise OpenLineageTransportError(
            f"OpenLineage publish failed after {self._max_attempts} attempts"
        ) from last_error


__all__ = [
    "OPENLINEAGE_API_VERSION",
    "MAX_OPENLINEAGE_EVENT_BYTES",
    "SUPPORTED_OPENLINEAGE_SCHEMA_VERSIONS",
    "OpenLineageSink",
    "OpenLineageTransport",
    "OpenLineageTransportError",
    "PublishReceipt",
    "validate_openlineage_event",
]
