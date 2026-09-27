"""Definition-only native Bundle portability for GenAI metadata."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from studio_core import WorkspaceId
from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.genai import (
    PromptAsset,
)
from studio_core.portability import RoninBundleManifest
from studio_storage.bundle import BundleFile, write_bundle
from studio_storage.bundle_payload import read_bundle_payload

from .genai import (
    SqliteGenAIStore,
    _agent_from_json,
    _index_from_json,
    _provider_from_json,
    _tool_from_json,
)

INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"
MEDIA = {
    "provider": "application/vnd.ronin.genai-provider+json",
    "prompt": "application/vnd.ronin.genai-prompt+json",
    "index": "application/vnd.ronin.genai-vector-index+json",
    "tool": "application/vnd.ronin.genai-tool+json",
    "agent": "application/vnd.ronin.genai-agent+json",
}


def _path(kind: str, ref: str) -> str:
    return f"objects/genai/{kind}/{hashlib.sha256(ref.encode()).hexdigest()}.json"


def _json(value: Any) -> bytes:
    return encode_canonical_json(value.to_payload())


def export_genai_bundle(
    workspace_id: WorkspaceId, store: SqliteGenAIStore, path: Path
) -> RoninBundleManifest:
    values: list[tuple[str, Sequence[Any]]] = [
        ("provider", store.list_providers(workspace_id)),
        ("prompt", store.list_prompts(workspace_id)),
        ("index", store.list_indexes(workspace_id)),
        ("tool", store.list_tools(workspace_id)),
        ("agent", store.list_agents(workspace_id)),
    ]
    objects: list[BundleInventoryObject] = []
    files: list[BundleFile] = []
    for kind, items in values:
        for item in items:
            identifier = str(getattr(item, "id", getattr(item, "version", "item")))
            ref = f"genai-{kind}:{workspace_id}/{identifier}"
            p = _path(kind, ref)
            objects.append(BundleInventoryObject(f"genai_{kind}", ref, p))
            files.append(BundleFile(p, MEDIA[kind], _json(item)))
    inventory = BundleInventory(tuple(objects))
    files.append(
        BundleFile(
            BUNDLE_INVENTORY_PATH,
            INVENTORY_MEDIA_TYPE,
            encode_canonical_json(inventory.to_payload()),
        )
    )
    return write_bundle(path, tuple(sorted(files, key=lambda item: item.path)))


def import_genai_bundle(
    path: Path, workspace_id: WorkspaceId, store: SqliteGenAIStore, *, now: str
) -> tuple[tuple[str, Any], ...]:
    inventory_file = read_bundle_payload(path, BUNDLE_INVENTORY_PATH)
    inventory = BundleInventory.from_payload(json.loads(inventory_file.file.data))
    parsed: list[tuple[str, Any]] = []
    for item in inventory.objects:
        payload = read_bundle_payload(path, item.path)
        if payload.manifest != inventory_file.manifest:
            raise ValueError("GenAI Bundle integrity mismatch")
        kind = item.kind.removeprefix("genai_")
        raw = payload.file.data.decode()
        parsers: dict[str, Callable[[str], Any]] = {
            "provider": _provider_from_json,
            "prompt": PromptAsset.from_json,
            "index": _index_from_json,
            "tool": _tool_from_json,
            "agent": _agent_from_json,
        }
        parser = parsers.get(kind)
        if parser is None:
            raise ValueError("unsupported GenAI Bundle object kind")
        value = parser(raw)
        parsed.append((kind, value))
    order = {"provider": 0, "prompt": 1, "index": 2, "tool": 3, "agent": 4}
    writers: dict[str, Callable[..., Any]] = {
        "provider": store.put_provider,
        "prompt": store.put_prompt,
        "index": store.put_index,
        "tool": store.put_tool,
        "agent": store.put_agent,
    }
    for kind, value in sorted(parsed, key=lambda item: order[item[0]]):
        writers[kind](workspace_id, value, now=now)
    return tuple(parsed)


__all__ = ("export_genai_bundle", "import_genai_bundle")
