"""Executable GenAI, RAG and agent runtime for Ronin Public v1."""

from .agent import AgentRunResult, AgentStep, ToolRegistry, ToolRuntime, run_agent
from .durable_agent import run_agent_durable
from .evaluation import (
    RAGEvaluation,
    RAGEvaluationReport,
    evaluate_rag_example,
    evaluate_rag_payload,
    summarize_rag_evaluation,
)
from .plugin import GenAIPlugin
from .provider import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    GenAIProviderDependencyError,
    GenAIProviderRuntime,
    OpenAICompatibleProvider,
)
from .qualification import ProviderQualification, qualify_model_payload, qualify_provider_model
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
    "ProviderQualification",
    "qualify_provider_model",
    "qualify_model_payload",
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
    "RAGEvaluation",
    "RAGEvaluationReport",
    "evaluate_rag_example",
    "summarize_rag_evaluation",
    "evaluate_rag_payload",
    "GenAIPlugin",
    "run_agent_durable",
)
