"""Bounded provider-neutral agent runtime over declared Ronin tool contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from studio_core.genai import AgentDefinition, GenAIModel, PromptAsset, ToolContract, ToolId

from .provider import ChatMessage, GenAIProviderRuntime


@runtime_checkable
class ToolRuntime(Protocol):
    contract: ToolContract

    def invoke(self, payload: Mapping[str, object]) -> Mapping[str, object]: ...


class ToolRegistry:
    def __init__(self, tools: tuple[ToolRuntime, ...] = ()) -> None:
        self._tools: dict[ToolId, ToolRuntime] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: ToolRuntime) -> None:
        identifier = tool.contract.id
        if identifier in self._tools:
            raise ValueError(f"duplicate tool runtime: {identifier}")
        self._tools[identifier] = tool

    def require(self, tool_id: ToolId) -> ToolRuntime:
        try:
            return self._tools[tool_id]
        except KeyError as exc:
            raise KeyError(f"tool runtime is not registered: {tool_id}") from exc


@dataclass(frozen=True, slots=True)
class AgentStep:
    step: int
    kind: str
    tool_id: ToolId | None = None


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    answer: str
    steps: tuple[AgentStep, ...]


def _render_agent_prompt(prompt: PromptAsset, user_input: str) -> str:
    values = {"input": user_input}
    missing = [name for name in prompt.parameter_names if name not in values]
    if missing:
        raise ValueError(f"agent prompt is missing parameters: {missing}")
    try:
        rendered = prompt.template.format_map(values)
    except (KeyError, ValueError) as exc:
        raise ValueError("agent prompt template could not be rendered") from exc
    if not rendered.strip():
        raise ValueError("agent rendered prompt must not be empty")
    return rendered


def _parse_action(content: str) -> dict[str, object]:
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("agent model response must be a JSON action object") from exc
    if not isinstance(value, dict):
        raise ValueError("agent model response must be a JSON object")
    action_type = value.get("type")
    if action_type == "final":
        if set(value) != {"type", "answer"} or not isinstance(value.get("answer"), str):
            raise ValueError("agent final action must contain only string answer")
    elif action_type == "tool":
        if set(value) != {"type", "tool_id", "input"}:
            raise ValueError("agent tool action has invalid shape")
        if not isinstance(value.get("tool_id"), str) or not isinstance(value.get("input"), dict):
            raise ValueError("agent tool action requires string tool_id and object input")
    else:
        raise ValueError("agent action type must be 'tool' or 'final'")
    return value


def run_agent(
    definition: AgentDefinition,
    prompt: PromptAsset,
    model: GenAIModel,
    provider: GenAIProviderRuntime,
    tools: ToolRegistry,
    user_input: str,
    *,
    allow_non_idempotent: bool = False,
) -> AgentRunResult:
    """Run a strict bounded tool loop without granting undeclared tool authority."""

    if not user_input or "\x00" in user_input:
        raise ValueError("agent input must be non-empty")
    if definition.provider_id != model.provider_id or definition.model_id != model.model_id:
        raise ValueError("agent model does not match definition")
    if definition.prompt_id != prompt.id or definition.prompt_version != prompt.version:
        raise ValueError("agent prompt does not match definition")
    if "chat" not in model.capabilities:
        raise ValueError("agent model must advertise chat capability")

    allowed_tools = set(definition.tool_ids)
    system = (
        _render_agent_prompt(prompt, user_input)
        + "\n\nReturn only JSON. Use {\"type\":\"tool\",\"tool_id\":\"...\",\"input\":{...}} "
        + "to call a tool or {\"type\":\"final\",\"answer\":\"...\"} to finish."
    )
    messages: list[ChatMessage] = [
        ChatMessage("system", system),
        ChatMessage("user", user_input),
    ]
    steps: list[AgentStep] = []

    for step_index in range(1, definition.max_steps + 1):
        result = provider.chat(model, tuple(messages))
        action = _parse_action(result.content)
        if action["type"] == "final":
            answer = action["answer"]
            assert isinstance(answer, str)
            steps.append(AgentStep(step_index, "final"))
            return AgentRunResult(answer, tuple(steps))

        raw_tool_id = action["tool_id"]
        payload = action["input"]
        assert isinstance(raw_tool_id, str)
        assert isinstance(payload, dict)
        tool_id = ToolId(raw_tool_id)
        if tool_id not in allowed_tools:
            raise PermissionError(f"agent attempted undeclared tool: {tool_id}")
        runtime = tools.require(tool_id)
        if runtime.contract.side_effect == "non_idempotent" and not allow_non_idempotent:
            raise PermissionError(
                f"non-idempotent tool requires explicit execution authorization: {tool_id}"
            )
        output = runtime.invoke(payload)
        if not isinstance(output, Mapping):
            raise TypeError("tool runtime must return a mapping")
        steps.append(AgentStep(step_index, "tool", tool_id))
        messages.append(ChatMessage("assistant", result.content))
        messages.append(
            ChatMessage(
                "user",
                json.dumps(
                    {"tool_result": {"tool_id": tool_id.value, "output": dict(output)}},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )

    raise RuntimeError(f"agent exceeded max_steps={definition.max_steps} without final answer")


__all__ = (
    "AgentRunResult",
    "AgentStep",
    "ToolRegistry",
    "ToolRuntime",
    "run_agent",
)
