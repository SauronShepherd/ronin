from __future__ import annotations

from pathlib import Path

import pytest

from studio_core import AssetId, AssetRef, AssetRevision, AssetVersion, CatalogAsset, Workspace, WorkspaceId
from studio_core.connections import SecretRef
from studio_core.genai import (
    AgentDefinition,
    AgentId,
    ModelProvider,
    PromptAsset,
    PromptId,
    PromptVersion,
    ProviderId,
    ToolContract,
    ToolId,
    VectorIndexDefinition,
    VectorIndexId,
)
from studio_orchestrator import Instant
from studio_storage.catalog import SqliteCatalogStore
from studio_storage.genai import GenAIConflict, SqliteGenAIStore
from studio_storage.workspaces import SqliteWorkspaceStore

_NOW = Instant("2026-09-12T00:00:00.000000Z")
_WS = WorkspaceId("ws-1")
_SOURCE = AssetRef(AssetId("docs"), AssetVersion("v1"))


def _store(path: Path) -> SqliteGenAIStore:
    workspaces = SqliteWorkspaceStore(path, migration_now=_NOW)
    workspaces.create_workspace(Workspace(_WS, "Workspace"), now=_NOW)
    catalog = SqliteCatalogStore(path, migration_now=_NOW)
    catalog.create_asset(_WS, CatalogAsset(AssetId("docs"), "dataset", "Documents"), now=_NOW)
    catalog.put_revision(_WS, AssetRevision(_SOURCE, content_digest="sha256:docs"), now=_NOW)
    return SqliteGenAIStore(path, migration_now=_NOW)


def test_provider_persists_only_secret_reference(tmp_path: Path) -> None:
    store = _store(tmp_path / "ronin.sqlite3")
    provider = ModelProvider(
        ProviderId("provider-1"),
        adapter="openai-compatible",
        endpoint="https://example.invalid/v1",
        secret_ref=SecretRef("secret://llm/api-key"),
    )

    store.put_provider(_WS, provider, now=_NOW)

    assert store.get_provider(_WS, provider.id) == provider


def test_prompt_version_is_immutable(tmp_path: Path) -> None:
    store = _store(tmp_path / "ronin.sqlite3")
    first = PromptAsset(PromptId("prompt-1"), PromptVersion("1"), "Answer {question}", ("question",))
    second = PromptAsset(PromptId("prompt-1"), PromptVersion("1"), "Changed {question}", ("question",))
    store.put_prompt(_WS, first, now=_NOW)

    with pytest.raises(GenAIConflict):
        store.put_prompt(_WS, second, now=_NOW)


def test_vector_index_requires_governed_source_and_provider(tmp_path: Path) -> None:
    store = _store(tmp_path / "ronin.sqlite3")
    provider = ModelProvider(ProviderId("provider-1"), adapter="openai-compatible")
    store.put_provider(_WS, provider, now=_NOW)
    index = VectorIndexDefinition(
        VectorIndexId("index-1"),
        _SOURCE,
        provider.id,
        "embedding-model",
        ("text",),
    )

    store.put_index(_WS, index, now=_NOW)

    assert store.get_index(_WS, index.id) == index


def test_agent_requires_registered_prompt_provider_and_tools(tmp_path: Path) -> None:
    store = _store(tmp_path / "ronin.sqlite3")
    provider = ModelProvider(ProviderId("provider-1"), adapter="openai-compatible")
    prompt = PromptAsset(PromptId("prompt-1"), PromptVersion("1"), "Use tools safely")
    tool = ToolContract(ToolId("tool-1"), "Lookup", "schema://lookup-in", "schema://lookup-out")
    store.put_provider(_WS, provider, now=_NOW)
    store.put_prompt(_WS, prompt, now=_NOW)
    store.put_tool(_WS, tool, now=_NOW)
    agent = AgentDefinition(
        AgentId("agent-1"),
        "Assistant",
        provider.id,
        "chat-model",
        prompt.id,
        prompt.version,
        (tool.id,),
        4,
    )

    store.put_agent(_WS, agent, now=_NOW)

    assert store.get_agent(_WS, agent.id) == agent
