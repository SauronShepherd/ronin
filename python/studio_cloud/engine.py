"""Provider-neutral cloud topology model and deterministic local emulator.

The engine deliberately has no SDK dependencies. Provider adapters can implement
the same resource types later, while Terraform and the visual editor consume the
stable topology contract.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CATALOG: dict[str, dict[str, Any]] = {
    "aws.s3.bucket": {
        "label": "S3 bucket",
        "category": "storage",
        "terraform": "aws_s3_bucket",
        "properties": {"bucket": "string", "force_destroy": "boolean"},
        "backends": ["in-memory", "floci", "localstack"],
    },
    "aws.lambda.function": {
        "label": "Lambda function",
        "category": "compute",
        "terraform": "aws_lambda_function",
        "properties": {
            "function_name": "string",
            "runtime": "string",
            "handler": "string",
            "filename": "string",
        },
        "backends": ["in-memory", "floci", "localstack"],
    },
    "aws.sqs.queue": {
        "label": "SQS queue",
        "category": "messaging",
        "terraform": "aws_sqs_queue",
        "properties": {"name": "string", "fifo_queue": "boolean"},
        "backends": ["in-memory", "floci", "localstack"],
    },
    "aws.dynamodb.table": {
        "label": "DynamoDB table",
        "category": "database",
        "terraform": "aws_dynamodb_table",
        "properties": {"name": "string", "hash_key": "string", "billing_mode": "string"},
        "backends": ["in-memory", "floci", "localstack"],
    },
}


@dataclass(frozen=True, slots=True)
class CloudResource:
    id: str
    type: str
    name: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CloudTopology:
    resources: tuple[CloudResource, ...] = ()
    edges: tuple[tuple[str, str], ...] = ()

    def validate(self) -> list[str]:
        errors: list[str] = []
        ids = {item.id for item in self.resources}
        if len(ids) != len(self.resources):
            errors.append("resource ids must be unique")
        for resource in self.resources:
            if resource.type not in CATALOG:
                errors.append(f"unsupported resource type: {resource.type}")
            if not resource.id or not resource.name:
                errors.append("resource id and name are required")
            if any(
                not isinstance(value, (str, bool, int, float))
                for value in resource.properties.values()
            ):
                errors.append(f"resource properties must be scalar: {resource.id}")
            schema = CATALOG.get(resource.type, {}).get("properties", {})
            for key, value in resource.properties.items():
                expected = schema.get(key)
                if expected == "string" and not isinstance(value, str):
                    errors.append(f"property {key} on {resource.id} must be a string")
                if expected == "boolean" and not isinstance(value, bool):
                    errors.append(f"property {key} on {resource.id} must be boolean")
        for source, target in self.edges:
            if source not in ids or target not in ids:
                errors.append(f"edge references an unknown resource: {source}->{target}")
        return errors


class CloudEmulator:
    """Small stateful emulator suitable for local tests and Terraform acceptance."""

    def __init__(self) -> None:
        self._state: dict[str, dict[str, Any]] = {}

    def apply(self, topology: CloudTopology) -> dict[str, Any]:
        errors = topology.validate()
        if errors:
            raise ValueError("invalid topology: " + "; ".join(errors))
        self._state = {
            r.id: {"id": r.id, "type": r.type, "name": r.name, **r.properties}
            for r in topology.resources
        }
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {"resources": [dict(value) for value in self._state.values()]}

    def plan(self, topology: CloudTopology) -> dict[str, Any]:
        errors = topology.validate()
        if errors:
            return {"valid": False, "errors": errors, "create": []}
        desired = {resource.id for resource in topology.resources}
        current = set(self._state)
        return {
            "valid": True,
            "errors": [],
            "create": sorted(desired - current),
            "destroy": sorted(current - desired),
            "update": sorted(desired & current),
        }

    def refresh(self) -> dict[str, Any]:
        return self.snapshot()

    def destroy(self) -> dict[str, Any]:
        removed = sorted(self._state)
        self._state.clear()
        return {"destroyed": removed, **self.snapshot()}

    def import_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        resources = snapshot.get("resources", [])
        if not isinstance(resources, list):
            raise ValueError("snapshot.resources must be a list")
        self._state = {str(item["id"]): dict(item) for item in resources}
        return self.snapshot()


def export_terraform(topology: CloudTopology) -> str:
    errors = topology.validate()
    if errors:
        raise ValueError("invalid topology: " + "; ".join(errors))
    blocks: list[str] = []
    for resource in topology.resources:
        tf_type = CATALOG[resource.type]["terraform"]
        properties = dict(resource.properties)
        if resource.type == "aws.s3.bucket":
            properties.setdefault("bucket", resource.name)
        elif resource.type == "aws.sqs.queue":
            properties.setdefault("name", resource.name)
        lines = [f'resource "{tf_type}" "{resource.name}" {{']
        for key, value in sorted(properties.items()):
            rendered = f'"{value}"' if isinstance(value, str) else str(value).lower()
            lines.append(f"  {key} = {rendered}")
        lines.append("}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def import_terraform(hcl: str) -> CloudTopology:
    """Import the safe, scalar resource subset emitted by Cloud Studio.

    This parser intentionally rejects interpolation, nested blocks, expressions,
    and unknown resource types. It never evaluates HCL or executes Terraform.
    """
    resources: list[CloudResource] = []
    block_pattern = re.compile(
        r'resource\s+"(?P<type>[^"]+)"\s+"(?P<name>[^"]+)"\s*\{(?P<body>.*?)\}',
        re.DOTALL,
    )
    for match in block_pattern.finditer(hcl):
        terraform_type = match.group("type")
        catalog_entry = next(
            (key for key, value in CATALOG.items() if value["terraform"] == terraform_type), None
        )
        if catalog_entry is None:
            raise ValueError(f"unsupported Terraform resource type: {terraform_type}")
        properties: dict[str, Any] = {}
        for line in match.group("body").splitlines():
            line = line.strip()
            if not line:
                continue
            property_match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)", line)
            if property_match is None:
                raise ValueError("only scalar property assignments are supported")
            key, raw_value = property_match.groups()
            if raw_value.startswith('"') and raw_value.endswith('"'):
                properties[key] = raw_value[1:-1]
            elif raw_value in {"true", "false"}:
                properties[key] = raw_value == "true"
            elif re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", raw_value):
                properties[key] = float(raw_value) if "." in raw_value else int(raw_value)
            else:
                raise ValueError("expressions and nested values are not supported")
        resources.append(
            CloudResource(
                id=f"{catalog_entry.replace('.', '_')}_{len(resources) + 1}",
                type=catalog_entry,
                name=match.group("name"),
                properties=properties,
            )
        )
    if not resources and hcl.strip():
        raise ValueError("no supported Cloud Studio resources found")
    topology = CloudTopology(tuple(resources))
    errors = topology.validate()
    if errors:
        raise ValueError("invalid imported topology: " + "; ".join(errors))
    return topology


class SnapshotStore:
    """Atomic JSON snapshot storage scoped to a Cloud Studio workspace."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, workspace: str) -> Path:
        safe = "".join(char for char in workspace if char.isalnum() or char in "-_ ").strip()
        if not safe:
            raise ValueError("workspace must contain at least one safe character")
        if safe != workspace.strip():
            raise ValueError("workspace contains unsafe characters")
        return self.root / f"{safe}.json"

    def save(self, workspace: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        target = self._path(workspace)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")
        temporary.replace(target)
        return snapshot

    def load(self, workspace: str) -> dict[str, Any] | None:
        target = self._path(workspace)
        if not target.exists():
            return None
        value = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("snapshot must be a JSON object")
        return value
