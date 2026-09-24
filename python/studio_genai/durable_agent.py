"""Application helper for bounded agent execution with durable safe evidence."""

from __future__ import annotations

from studio_core import WorkspaceId
from studio_core.genai import AgentDefinition, GenAIModel, PromptAsset
from studio_orchestrator import Instant
from studio_storage.genai import SqliteGenAIStore

from .agent import AgentRunResult, ToolRegistry, run_agent
from .provider import GenAIProviderRuntime


def run_agent_durable(
    store: SqliteGenAIStore,
    workspace_id: WorkspaceId,
    run_id: str,
    definition: AgentDefinition,
    prompt: PromptAsset,
    model: GenAIModel,
    provider: GenAIProviderRuntime,
    tools: ToolRegistry,
    user_input: str,
    *,
    now: Instant | str,
    timeout_seconds: float | None = None,
    allow_non_idempotent: bool = False,
    authorize_requirements: object | None = None,
) -> AgentRunResult:
    """Execute an agent and durably record only bounded evidence metadata."""

    kwargs: dict[str, object] = {
        "timeout_seconds": timeout_seconds,
        "allow_non_idempotent": allow_non_idempotent,
    }
    if callable(authorize_requirements):
        kwargs["authorize_requirements"] = authorize_requirements
    try:
        result = run_agent(
            definition,
            prompt,
            model,
            provider,
            tools,
            user_input,
            **kwargs,
        )
    except TimeoutError:
        store.put_agent_run(
            workspace_id,
            run_id,
            definition.id.value,
            "timeout",
            {"schema": "ronin.genai-agent-evidence/v1", "step_count": 0},
            now=now,
        )
        raise
    except Exception:
        store.put_agent_run(
            workspace_id,
            run_id,
            definition.id.value,
            "failed",
            {"schema": "ronin.genai-agent-evidence/v1", "step_count": 0},
            now=now,
        )
        raise
    store.put_agent_run(
        workspace_id,
        run_id,
        definition.id.value,
        "completed",
        result.evidence_payload(),
        now=now,
    )
    return result


__all__ = ("run_agent_durable",)
