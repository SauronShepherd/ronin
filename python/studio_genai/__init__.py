"""Executable GenAI, RAG and agent runtime for Ronin Public v1."""

from .agent import AgentRunResult, AgentStep, ToolRegistry, ToolRuntime, run_agent
from .provider import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    GenAIProviderDependencyError,
    GenAIProviderRuntime,
    OpenAICompatibleProvider,
)
from .rag import RAGResult, VectorIndexBuildResult, build_vector_index, run_rag
from .vector_store import SqliteVectorStore, VectorChunk, VectorMatch

__all__ = (
    "AgentRunResult",
    "AgentStep",
    "ChatMessage",
    "ChatResult",
    "EmbeddingResult",
    "GenAIProviderDependencyError",
    "GenAIProviderRuntime",
    "OpenAICompatibleProvider",
    "RAGResult",
    "SqliteVectorStore",
    "ToolRegistry",
    "ToolRuntime",
    "VectorChunk",
    "VectorIndexBuildResult",
    "VectorMatch",
    "build_vector_index",
    "run_agent",
    "run_rag",
)
