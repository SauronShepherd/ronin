from __future__ import annotations

from pathlib import Path

import pytest
from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    Workspace,
    WorkspaceId,
)
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
from studio_genai.agent import ToolRegistry
from studio_genai.provider import _MAX_PROVIDER_RESPONSE_BYTES, _read_json_response
from studio_orchestrator import Instant
from studio_storage.catalog import SqliteCatalogStore
from studio_storage.genai import GenAIConflict, SqliteGenAIStore
from studio_storage.genai_bundle import export_genai_bundle, import_genai_bundle
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


def test_agent_run_evidence_is_durable_and_secret_safe(tmp_path: Path) -> None:
    store = _store(tmp_path / "ronin.sqlite3")
    evidence = {"schema": "ronin.genai-agent-evidence/v1", "step_count": 1}
    store.put_agent_run(_WS, "run-1", "agent-1", "completed", evidence, now=_NOW)
    assert store.get_agent_run(_WS, "run-1") == {
        "run_id": "run-1",
        "agent_id": "agent-1",
        "status": "completed",
        "evidence": evidence,
    }
    assert store.put_agent_run(_WS, "run-1", "agent-1", "completed", evidence, now=_NOW) == {
        "run_id": "run-1",
        "agent_id": "agent-1",
        "status": "completed",
        "evidence": evidence,
    }
    with pytest.raises(GenAIConflict, match="agent run identity"):
        store.put_agent_run(_WS, "run-1", "agent-1", "failed", evidence, now=_NOW)
    with pytest.raises(ValueError, match="must not contain"):
        store.put_agent_run(_WS, "run-2", "agent-1", "completed", {"answer": "secret"}, now=_NOW)


def test_prompt_version_is_immutable(tmp_path: Path) -> None:
    store = _store(tmp_path / "ronin.sqlite3")
    first = PromptAsset(
        PromptId("prompt-1"), PromptVersion("1"), "Answer {question}", ("question",)
    )
    second = PromptAsset(
        PromptId("prompt-1"), PromptVersion("1"), "Changed {question}", ("question",)
    )
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
    assert store.delete_index(_WS, index.id) is True
    assert store.get_index(_WS, index.id) is None
    assert store.delete_index(_WS, index.id) is False


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
    assert store.delete_agent(_WS, agent.id) is True
    assert store.get_agent(_WS, agent.id) is None
    assert store.delete_agent(_WS, agent.id) is False
    assert store.delete_tool(_WS, tool.id) is True
    assert store.get_tool(_WS, tool.id) is None
    assert store.delete_tool(_WS, tool.id) is False


def test_tool_registry_exposes_deterministic_contract_inventory() -> None:
    class Runtime:
        def __init__(self, contract: ToolContract) -> None:
            self.contract = contract

        def invoke(self, payload: dict[str, object]) -> dict[str, object]:
            return payload

    first = Runtime(ToolContract(ToolId("tool-b"), "B", "schema://in", "schema://out"))
    second = Runtime(ToolContract(ToolId("tool-a"), "A", "schema://in", "schema://out"))
    registry = ToolRegistry((first, second))
    assert tuple(item.id for item in registry.list_contracts()) == (
        ToolId("tool-a"),
        ToolId("tool-b"),
    )


def test_genai_definition_bundle_round_trip_preserves_secret_reference_only(tmp_path: Path) -> None:
    source = _store(tmp_path / "source.sqlite3")
    provider = ModelProvider(
        ProviderId("provider-1"),
        adapter="openai-compatible",
        secret_ref=SecretRef("secret://llm/key"),
    )
    prompt = PromptAsset(PromptId("prompt-1"), PromptVersion("1"), "Answer safely")
    tool = ToolContract(ToolId("tool-1"), "Lookup", "schema://in", "schema://out")
    source.put_provider(_WS, provider, now=_NOW)
    source.put_prompt(_WS, prompt, now=_NOW)
    source.put_tool(_WS, tool, now=_NOW)
    bundle = tmp_path / "genai.roninbundle"
    export_genai_bundle(_WS, source, bundle)
    target = _store(tmp_path / "target.sqlite3")
    import_genai_bundle(bundle, _WS, target, now=_NOW)
    assert target.get_provider(_WS, provider.id) == provider
    assert target.get_prompt(_WS, prompt.id, prompt.version) == prompt
    assert target.get_tool(_WS, tool.id) == tool


class _ChunkedResponse:
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self.chunks = chunks

    def iter_bytes(self):
        yield from self.chunks


def test_provider_response_reader_fails_before_materializing_oversized_body() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        _read_json_response(_ChunkedResponse((b"{}", b"x" * _MAX_PROVIDER_RESPONSE_BYTES)))
