"""Deterministic vector indexing and retrieval-augmented generation runtime."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from studio_core.genai import (
    GenAIModel,
    PromptAsset,
    RAGDefinition,
    VectorIndexDefinition,
)

from .provider import ChatMessage, ChatResult, GenAIProviderRuntime
from .vector_store import SqliteVectorStore, VectorChunk, VectorMatch


@dataclass(frozen=True, slots=True)
class VectorIndexBuildResult:
    index_id: str
    chunks: int
    dimensions: int


@dataclass(frozen=True, slots=True)
class RAGResult:
    answer: ChatResult
    matches: tuple[VectorMatch, ...]
    rendered_prompt: str


def _chunk_text(text: str, *, size: int, overlap: int) -> tuple[str, ...]:
    if not text:
        return ()
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return tuple(chunks)


def _chunk_id(index: VectorIndexDefinition, row_index: int, chunk_index: int, text: str) -> str:
    digest = hashlib.sha256(
        f"{index.id.value}\n{row_index}\n{chunk_index}\n{text}".encode("utf-8")
    ).hexdigest()
    return f"chunk-{digest[:32]}"


def build_vector_index(
    definition: VectorIndexDefinition,
    rows: Sequence[Mapping[str, object]],
    embedding_model: GenAIModel,
    provider: GenAIProviderRuntime,
    store: SqliteVectorStore,
    *,
    batch_size: int = 128,
) -> VectorIndexBuildResult:
    """Materialize one metadata-defined vector index into the reference store."""

    if embedding_model.provider_id != definition.provider_id:
        raise ValueError("embedding model provider does not match vector index definition")
    if embedding_model.model_id != definition.embedding_model_id:
        raise ValueError("embedding model id does not match vector index definition")
    if "embedding" not in embedding_model.capabilities:
        raise ValueError("vector index model does not advertise embedding capability")
    if batch_size < 1 or batch_size > 2048:
        raise ValueError("embedding batch_size must be between 1 and 2048")

    pending_texts: list[str] = []
    pending_meta: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    chunks: list[VectorChunk] = []

    def flush() -> None:
        if not pending_texts:
            return
        result = provider.embed(embedding_model, tuple(pending_texts))
        if len(result.vectors) != len(pending_texts):
            raise ValueError("embedding provider returned unexpected vector count")
        for (chunk_id, metadata), text, vector in zip(
            pending_meta,
            pending_texts,
            result.vectors,
            strict=True,
        ):
            chunks.append(VectorChunk(definition.id, chunk_id, text, vector, metadata))
        pending_texts.clear()
        pending_meta.clear()

    for row_index, row in enumerate(rows):
        missing_text = [name for name in definition.text_fields if name not in row]
        missing_metadata = [name for name in definition.metadata_fields if name not in row]
        if missing_text or missing_metadata:
            raise ValueError(
                f"vector source row {row_index} is missing fields: {missing_text + missing_metadata}"
            )
        combined = "\n".join(str(row[name]) for name in definition.text_fields if row[name] is not None)
        metadata = tuple(
            sorted(
                (name, "" if row[name] is None else str(row[name]))
                for name in definition.metadata_fields
            )
        )
        for chunk_index, text in enumerate(
            _chunk_text(
                combined,
                size=definition.chunk_size,
                overlap=definition.chunk_overlap,
            )
        ):
            pending_texts.append(text)
            pending_meta.append((_chunk_id(definition, row_index, chunk_index, text), metadata))
            if len(pending_texts) >= batch_size:
                flush()
    flush()
    if not chunks:
        raise ValueError("vector index source produced no non-empty chunks")
    dimensions = {len(chunk.vector) for chunk in chunks}
    if len(dimensions) != 1:
        raise ValueError("embedding provider returned inconsistent vector dimensions")
    store.replace_index(definition.id, tuple(chunks))
    return VectorIndexBuildResult(definition.id.value, len(chunks), next(iter(dimensions)))


def _render_prompt(
    prompt: PromptAsset,
    *,
    question: str,
    context: str,
    parameters: Mapping[str, str] | None,
) -> str:
    values = dict(parameters or {})
    values.setdefault("question", question)
    values.setdefault("context", context)
    missing = [name for name in prompt.parameter_names if name not in values]
    if missing:
        raise ValueError(f"RAG prompt is missing parameters: {missing}")
    allowed = set(prompt.parameter_names) | {"question", "context"}
    unexpected = set(values) - allowed
    if unexpected:
        raise ValueError(f"RAG prompt received undeclared parameters: {sorted(unexpected)}")
    try:
        rendered = prompt.template.format_map(values)
    except (KeyError, ValueError) as exc:
        raise ValueError("RAG prompt template could not be rendered") from exc
    if not rendered.strip():
        raise ValueError("RAG rendered prompt must not be empty")
    return rendered


def run_rag(
    definition: RAGDefinition,
    index_definition: VectorIndexDefinition,
    prompt: PromptAsset,
    embedding_model: GenAIModel,
    chat_model: GenAIModel,
    provider: GenAIProviderRuntime,
    store: SqliteVectorStore,
    question: str,
    *,
    parameters: Mapping[str, str] | None = None,
) -> RAGResult:
    """Retrieve indexed chunks and execute one bounded provider-neutral RAG call."""

    if not question or "\x00" in question:
        raise ValueError("RAG question must be non-empty")
    if definition.index_id != index_definition.id:
        raise ValueError("RAG definition references a different vector index")
    if definition.prompt_id != prompt.id or definition.prompt_version != prompt.version:
        raise ValueError("RAG prompt identity does not match definition")
    if definition.provider_id != chat_model.provider_id or definition.model_id != chat_model.model_id:
        raise ValueError("RAG chat model does not match definition")
    if embedding_model.provider_id != index_definition.provider_id:
        raise ValueError("RAG embedding model provider does not match index")
    query_vector = provider.embed(embedding_model, (question,)).vectors[0]
    matches = store.search(index_definition.id, query_vector, top_k=definition.top_k)
    context = "\n\n".join(
        f"[{match.chunk.chunk_id}] {match.chunk.text}" for match in matches
    )
    rendered = _render_prompt(
        prompt,
        question=question,
        context=context,
        parameters=parameters,
    )
    answer = provider.chat(chat_model, (ChatMessage("user", rendered),))
    return RAGResult(answer, matches, rendered)


__all__ = (
    "RAGResult",
    "VectorIndexBuildResult",
    "build_vector_index",
    "run_rag",
)
