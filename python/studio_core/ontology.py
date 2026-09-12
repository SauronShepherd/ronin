"""Provider-neutral ontology and virtual knowledge-graph contracts for Public v1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json
from .catalog import AssetRef
from .grants import Requirement

LinkCardinality: TypeAlias = Literal[
    "one-to-one", "one-to-many", "many-to-one", "many-to-many"
]


def _require_text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


@dataclass(frozen=True, order=True, slots=True)
class OntologyId:
    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "ontology id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True, slots=True)
class PropertyDefinition:
    name: str
    data_type: str
    source_field: str
    required: bool = False

    def __post_init__(self) -> None:
        _require_text(self.name, "ontology property name")
        _require_text(self.data_type, "ontology property data_type")
        _require_text(self.source_field, "ontology property source_field")

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "data_type": self.data_type,
            "source_field": self.source_field,
            "required": self.required,
        }

    @classmethod
    def from_payload(cls, payload: object) -> PropertyDefinition:
        if not isinstance(payload, Mapping) or set(payload) != {
            "name",
            "data_type",
            "source_field",
            "required",
        }:
            raise ValueError("ontology property has invalid shape")
        name = payload["name"]
        data_type = payload["data_type"]
        source_field = payload["source_field"]
        required = payload["required"]
        if not all(isinstance(value, str) for value in (name, data_type, source_field)):
            raise ValueError("ontology property string fields are invalid")
        if not isinstance(required, bool):
            raise ValueError("ontology property required must be boolean")
        return cls(cast(str, name), cast(str, data_type), cast(str, source_field), required)


@dataclass(frozen=True, slots=True)
class ObjectType:
    name: str
    backing_asset: AssetRef
    key_fields: tuple[str, ...]
    properties: tuple[PropertyDefinition, ...]

    def __post_init__(self) -> None:
        _require_text(self.name, "object type name")
        keys = tuple(_require_text(value, "object key field") for value in self.key_fields)
        if not keys or len(keys) != len(set(keys)):
            raise ValueError("object type requires unique key_fields")
        properties = tuple(sorted(self.properties, key=lambda item: item.name))
        names = [item.name for item in properties]
        source_fields = [item.source_field for item in properties]
        if len(names) != len(set(names)):
            raise ValueError("object property names must be unique")
        missing = set(keys) - set(source_fields)
        if missing:
            raise ValueError("object key_fields must be represented by properties")
        object.__setattr__(self, "key_fields", keys)
        object.__setattr__(self, "properties", properties)

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "backing_asset": self.backing_asset.to_payload(),
            "key_fields": list(self.key_fields),
            "properties": [item.to_payload() for item in self.properties],
        }

    @classmethod
    def from_payload(cls, payload: object) -> ObjectType:
        if not isinstance(payload, Mapping) or set(payload) != {
            "name",
            "backing_asset",
            "key_fields",
            "properties",
        }:
            raise ValueError("object type has invalid shape")
        name = payload["name"]
        keys = payload["key_fields"]
        properties = payload["properties"]
        if not isinstance(name, str):
            raise ValueError("object type name must be string")
        if not isinstance(keys, list) or not all(isinstance(value, str) for value in keys):
            raise ValueError("object key_fields must be string array")
        if not isinstance(properties, list):
            raise ValueError("object properties must be array")
        return cls(
            name,
            AssetRef.from_payload(payload["backing_asset"]),
            tuple(keys),
            tuple(PropertyDefinition.from_payload(item) for item in properties),
        )


@dataclass(frozen=True, slots=True)
class LinkType:
    name: str
    source_type: str
    target_type: str
    cardinality: LinkCardinality
    source_fields: tuple[str, ...]
    target_fields: tuple[str, ...]
    backing_asset: AssetRef | None = None

    def __post_init__(self) -> None:
        _require_text(self.name, "link type name")
        _require_text(self.source_type, "link source type")
        _require_text(self.target_type, "link target type")
        if self.cardinality not in {"one-to-one", "one-to-many", "many-to-one", "many-to-many"}:
            raise ValueError("unsupported link cardinality")
        source = tuple(_require_text(value, "link source field") for value in self.source_fields)
        target = tuple(_require_text(value, "link target field") for value in self.target_fields)
        if not source or len(source) != len(target):
            raise ValueError("link source_fields and target_fields must be non-empty and aligned")
        object.__setattr__(self, "source_fields", source)
        object.__setattr__(self, "target_fields", target)

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "source_type": self.source_type,
            "target_type": self.target_type,
            "cardinality": self.cardinality,
            "source_fields": list(self.source_fields),
            "target_fields": list(self.target_fields),
            "backing_asset": None if self.backing_asset is None else self.backing_asset.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: object) -> LinkType:
        if not isinstance(payload, Mapping) or set(payload) != {
            "name",
            "source_type",
            "target_type",
            "cardinality",
            "source_fields",
            "target_fields",
            "backing_asset",
        }:
            raise ValueError("link type has invalid shape")
        name = payload["name"]
        source_type = payload["source_type"]
        target_type = payload["target_type"]
        cardinality = payload["cardinality"]
        source_fields = payload["source_fields"]
        target_fields = payload["target_fields"]
        backing_asset = payload["backing_asset"]
        if not all(isinstance(value, str) for value in (name, source_type, target_type, cardinality)):
            raise ValueError("link type identity fields must be strings")
        if cardinality not in {"one-to-one", "one-to-many", "many-to-one", "many-to-many"}:
            raise ValueError("unsupported link cardinality")
        if not isinstance(source_fields, list) or not all(isinstance(value, str) for value in source_fields):
            raise ValueError("link source_fields must be string array")
        if not isinstance(target_fields, list) or not all(isinstance(value, str) for value in target_fields):
            raise ValueError("link target_fields must be string array")
        return cls(
            cast(str, name),
            cast(str, source_type),
            cast(str, target_type),
            cast(LinkCardinality, cardinality),
            tuple(source_fields),
            tuple(target_fields),
            None if backing_asset is None else AssetRef.from_payload(backing_asset),
        )


@dataclass(frozen=True, slots=True)
class ActionType:
    name: str
    target_type: str
    input_fields: tuple[str, ...] = ()
    requirements: tuple[Requirement, ...] = ()
    write_asset: AssetRef | None = None
    idempotent: bool = False

    def __post_init__(self) -> None:
        _require_text(self.name, "ontology action name")
        _require_text(self.target_type, "ontology action target type")
        fields = tuple(sorted(_require_text(value, "ontology action input field") for value in self.input_fields))
        if len(fields) != len(set(fields)):
            raise ValueError("ontology action input fields must be unique")
        requirements = tuple(sorted(self.requirements, key=lambda item: item.canonical_key))
        if len(requirements) != len(set(item.canonical_key for item in requirements)):
            raise ValueError("ontology action requirements must be unique")
        object.__setattr__(self, "input_fields", fields)
        object.__setattr__(self, "requirements", requirements)

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "target_type": self.target_type,
            "input_fields": list(self.input_fields),
            "requirements": [item.to_payload() for item in self.requirements],
            "write_asset": None if self.write_asset is None else self.write_asset.to_payload(),
            "idempotent": self.idempotent,
        }

    @classmethod
    def from_payload(cls, payload: object) -> ActionType:
        if not isinstance(payload, Mapping) or set(payload) != {
            "name",
            "target_type",
            "input_fields",
            "requirements",
            "write_asset",
            "idempotent",
        }:
            raise ValueError("ontology action has invalid shape")
        name = payload["name"]
        target_type = payload["target_type"]
        input_fields = payload["input_fields"]
        requirements = payload["requirements"]
        write_asset = payload["write_asset"]
        idempotent = payload["idempotent"]
        if not isinstance(name, str) or not isinstance(target_type, str):
            raise ValueError("ontology action name/target_type must be strings")
        if not isinstance(input_fields, list) or not all(isinstance(value, str) for value in input_fields):
            raise ValueError("ontology action input_fields must be string array")
        if not isinstance(requirements, list):
            raise ValueError("ontology action requirements must be array")
        if not isinstance(idempotent, bool):
            raise ValueError("ontology action idempotent must be boolean")
        return cls(
            name,
            target_type,
            tuple(input_fields),
            tuple(Requirement.from_payload(item) for item in requirements),
            None if write_asset is None else AssetRef.from_payload(write_asset),
            idempotent,
        )


@dataclass(frozen=True, slots=True)
class OntologyDefinition:
    id: OntologyId
    version: str
    name: str
    object_types: tuple[ObjectType, ...]
    link_types: tuple[LinkType, ...] = ()
    actions: tuple[ActionType, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.version, "ontology version")
        _require_text(self.name, "ontology name")
        objects = tuple(sorted(self.object_types, key=lambda item: item.name))
        if not objects:
            raise ValueError("ontology requires at least one object type")
        object_names = [item.name for item in objects]
        if len(object_names) != len(set(object_names)):
            raise ValueError("ontology object type names must be unique")
        known = set(object_names)
        links = tuple(sorted(self.link_types, key=lambda item: item.name))
        if len(links) != len(set(item.name for item in links)):
            raise ValueError("ontology link type names must be unique")
        if any(link.source_type not in known or link.target_type not in known for link in links):
            raise ValueError("ontology link references unknown object type")
        actions = tuple(sorted(self.actions, key=lambda item: item.name))
        if len(actions) != len(set(item.name for item in actions)):
            raise ValueError("ontology action names must be unique")
        if any(action.target_type not in known for action in actions):
            raise ValueError("ontology action references unknown object type")
        object.__setattr__(self, "object_types", objects)
        object.__setattr__(self, "link_types", links)
        object.__setattr__(self, "actions", actions)

    def asset_refs(self) -> tuple[AssetRef, ...]:
        refs = {item.backing_asset for item in self.object_types}
        refs.update(link.backing_asset for link in self.link_types if link.backing_asset is not None)
        refs.update(action.write_asset for action in self.actions if action.write_asset is not None)
        return tuple(sorted(cast(set[AssetRef], refs)))

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id.value,
            "version": self.version,
            "name": self.name,
            "object_types": [item.to_payload() for item in self.object_types],
            "link_types": [item.to_payload() for item in self.link_types],
            "actions": [item.to_payload() for item in self.actions],
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> OntologyDefinition:
        if not isinstance(payload, Mapping) or set(payload) != {
            "id",
            "version",
            "name",
            "object_types",
            "link_types",
            "actions",
        }:
            raise ValueError("ontology definition has invalid shape")
        identifier = payload["id"]
        version = payload["version"]
        name = payload["name"]
        objects = payload["object_types"]
        links = payload["link_types"]
        actions = payload["actions"]
        if not all(isinstance(value, str) for value in (identifier, version, name)):
            raise ValueError("ontology identity fields must be strings")
        if not isinstance(objects, list) or not isinstance(links, list) or not isinstance(actions, list):
            raise ValueError("ontology collections must be arrays")
        return cls(
            OntologyId(cast(str, identifier)),
            cast(str, version),
            cast(str, name),
            tuple(ObjectType.from_payload(item) for item in objects),
            tuple(LinkType.from_payload(item) for item in links),
            tuple(ActionType.from_payload(item) for item in actions),
        )

    @classmethod
    def from_json(cls, payload: str) -> OntologyDefinition:
        return cls.from_payload(decode_canonical_json(payload))


@dataclass(frozen=True, order=True, slots=True)
class KnowledgeObjectRef:
    object_type: str
    key: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _require_text(self.object_type, "knowledge object type")
        key = tuple(sorted((_require_text(k, "object key name"), _require_text(v, "object key value")) for k, v in self.key))
        if not key or len(key) != len(set(k for k, _ in key)):
            raise ValueError("knowledge object key must be non-empty and unique")
        object.__setattr__(self, "key", key)
