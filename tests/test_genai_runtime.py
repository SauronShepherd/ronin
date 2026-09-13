from pathlib import Path

import pytest

from studio_core import AssetId, AssetRef, AssetVersion
from studio_core.genai import (
    AgentDefinition,
    AgentId,
    GenAIModel,
    PromptAsset,
    PromptId,
    PromptVersion,
    ProviderId,
    RAGDefinition,
    ToolContract,
    ToolId,
    VectorIndexDefinition,
    VectorIndexId,
)
from studio_genai import (
    ChatResult,
    EmbeddingResult,
    RAGResult,
    SqliteVectorStore,
    ToolRegistry,
    build_vector_index,
    run_agent,
    run_rag,
)


_PROVIDER = ProviderId("provider")
_EMBED = GenAIModel(_PROVIDER, "embed", frozenset({"embedding"}))
_CHAT = GenAIModel(_PROVIDER, "chat", frozenset({"chat"}))


class _Provider:
    def __init__(self, chat_results: list[str] | None = None) -> None:
        self.chat_results = list(chat_results or ["answer"])
        self.messages = []

    def embed(self, model, texts):
        del model
        vectors = []
        for text in texts:
            lowered = text.casefold()
            if "alpha" in lowered:
                vectors.append((1.0, 0.0))
            elif "beta" in lowered:
                vectors.append((0.0, 1.0))
            else:
                vectors.append((0.5, 0.5))
        return EmbeddingResult(tuple(vectors), "embed")

    def chat(self, model, messages):
        del model
        self.messages.append(tuple(messages))
        return ChatResult(self.chat_results.pop(0), "chat")


class _Tool:
    def __init__(self, side_effect: str = "none") -> None:
        self.contract = ToolContract(
            ToolId("lookup"),
            "Lookup",
            "schema://input",
            "schema://output",
            side_effect=side_effect,
        )
        self.calls = []

    def invoke(self, payload):
        self.calls.append(dict(payload))
        return {"value": "ok"}


def test_vector_index_and_rag_retrieve_relevant_context(tmp_path: Path) -> None:
    index = VectorIndexDefinition(
        VectorIndexId("docs"),
        AssetRef(AssetId("dataset"), AssetVersion("v1")),
        _PROVIDER,
        "embed",
        ("text",),
        ("source",),
        chunk_size=100,
        chunk_overlap=10,
    )
    store = SqliteVectorStore(tmp_path / "vectors.sqlite")
    provider = _Provider(["grounded answer"])
    built = build_vector_index(
        index,
        (
            {"text": "alpha document", "source": "a"},
            {"text": "beta document", "source": "b"},
        ),
        _EMBED,
        provider,
        store,
    )
    assert built.chunks == 2

    prompt = PromptAsset(
        PromptId("rag"),
        PromptVersion("1"),
        "Context:\n{context}\nQuestion: {question}",
        ("context", "question"),
    )
    definition = RAGDefinition(
        "Docs RAG",
        VectorIndexId("docs"),
        prompt.id,
        prompt.version,
        _PROVIDER,
        "chat",
        top_k=1,
    )
    result = run_rag(
        definition,
        index,
        prompt,
        _EMBED,
        _CHAT,
        provider,
        store,
        "tell me about alpha",
    )
    assert isinstance(result, RAGResult)
    assert result.answer.content == "grounded answer"
    assert "alpha document" in result.rendered_prompt
    assert result.matches[0].chunk.metadata == (("source", "a"),)


def test_agent_calls_only_declared_tool_then_finishes() -> None:
    prompt = PromptAsset(
        PromptId("agent-prompt"),
        PromptVersion("1"),
        "Handle {input}",
        ("input",),
    )
    definition = AgentDefinition(
        AgentId("agent"),
        "Agent",
        _PROVIDER,
        "chat",
        prompt.id,
        prompt.version,
        (ToolId("lookup"),),
        max_steps=3,
    )
    tool = _Tool()
    provider = _Provider(
        [
            '{"type":"tool","tool_id":"lookup","input":{"q":"alpha"}}',
            '{"type":"final","answer":"done"}',
        ]
    )
    result = run_agent(
        definition,
        prompt,
        _CHAT,
        provider,
        ToolRegistry((tool,)),
        "find alpha",
    )
    assert result.answer == "done"
    assert tuple(step.kind for step in result.steps) == ("tool", "final")
    assert tool.calls == [{"q": "alpha"}]


def test_agent_blocks_non_idempotent_tool_without_explicit_authorization() -> None:
    prompt = PromptAsset(
        PromptId("agent-prompt"),
        PromptVersion("1"),
        "Handle {input}",
        ("input",),
    )
    definition = AgentDefinition(
        AgentId("agent"),
        "Agent",
        _PROVIDER,
        "chat",
        prompt.id,
        prompt.version,
        (ToolId("lookup"),),
        max_steps=2,
    )
    provider = _Provider(['{"type":"tool","tool_id":"lookup","input":{}}'])
    with pytest.raises(PermissionError, match="non-idempotent"):
        run_agent(
            definition,
            prompt,
            _CHAT,
            provider,
            ToolRegistry((_Tool("non_idempotent"),)),
            "do something",
        )
