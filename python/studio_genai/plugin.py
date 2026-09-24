"""Plugin boundary for provider-neutral GenAI discovery."""

from __future__ import annotations

import json
from typing import Protocol, cast

from studio_core.genai import AgentDefinition, PromptAsset, ToolContract
from studio_core.plugins import PluginContext, PluginManifest, SurfaceContribution

from .evaluation import RAGEvaluationReport


class _GenAIService(Protocol):
    def providers(self, workspace_id: str) -> object: ...
    def health(self, workspace_id: str) -> object: ...
    def prompts(self, workspace_id: str) -> object: ...
    def put_prompt(self, workspace_id: str, prompt: PromptAsset) -> object: ...
    def indexes(self, workspace_id: str) -> object: ...
    def get_index(self, workspace_id: str, index_id: str) -> object: ...
    def tools(self, workspace_id: str) -> object: ...
    def get_tool(self, workspace_id: str, tool_id: str) -> object: ...
    def put_tool(self, workspace_id: str, tool: ToolContract, idempotency_key: str) -> object: ...
    def delete_tool(self, workspace_id: str, tool_id: str, idempotency_key: str) -> object: ...
    def agents(self, workspace_id: str) -> object: ...
    def get_agent(self, workspace_id: str, agent_id: str) -> object: ...
    def run_agent(self, workspace_id: str, agent_id: str, body: dict[str, object]) -> object: ...
    def put_agent(
        self, workspace_id: str, agent: AgentDefinition, idempotency_key: str
    ) -> object: ...
    def delete_agent(self, workspace_id: str, agent_id: str, idempotency_key: str) -> object: ...
    def agent_runs(self, workspace_id: str, agent_id: str) -> object: ...
    def get_agent_run(self, workspace_id: str, run_id: str) -> object: ...
    def evaluate_rag(self, workspace_id: str, body: dict[str, object]) -> object: ...
    def get_rag_evaluation(self, workspace_id: str, evaluation_id: str) -> object: ...
    def delete_index(self, workspace_id: str, index_id: str) -> object: ...
    def search_index(self, workspace_id: str, index_id: str, body: dict[str, object]) -> object: ...
    def build_index(self, workspace_id: str, index_id: str, body: dict[str, object]) -> object: ...


class GenAIPlugin:
    manifest = PluginManifest(
        id="com.sauronshepherd.ronin.genai",
        name="Ronin GenAI",
        version="0.1.0",
        plugin_api="1.0",
        host_requires=">=1,<2",
        capabilities=("genai.discovery",),
        permissions=("genai:read", "genai:write"),
        isolation="worker",
        surface_ids=(
            "genai.providers.v1",
            "genai.health.v1",
            "genai.prompts.v1",
            "genai.prompt.v1",
            "genai.indexes.v1",
            "genai.index.v1",
            "genai.index.delete.v1",
            "genai.index.query.v1",
            "genai.index.build.v1",
            "genai.tools.v1",
            "genai.tool.v1",
            "genai.tool.put.v1",
            "genai.tool.delete.v1",
            "genai.agents.v1",
            "genai.agent.v1",
            "genai.agent.run.v1",
            "genai.agent.run.get.v1",
            "genai.rag.evaluation.v1",
            "genai.rag.evaluation.get.v1",
            "genai.agent.put.v1",
            "genai.agent.delete.v1",
            "genai.agent.runs.v1",
            "genai.agent.run.v1",
        ),
    )

    def __init__(self) -> None:
        self._service: _GenAIService | None = None

    def register(self, context: PluginContext) -> None:
        self._service = cast(_GenAIService | None, context.services.get("genai"))
        context.contributions.add_permission("genai:read", context.plugin_id)
        context.contributions.add_permission("genai:write", context.plugin_id)
        for method, path, operation, handler in (
            ("GET", "/v1/workspaces/{workspace_id}/genai/providers", "providers", self.providers),
            ("GET", "/v1/workspaces/{workspace_id}/genai/health", "health", self.health),
            ("GET", "/v1/workspaces/{workspace_id}/genai/prompts", "prompts", self.prompts),
            (
                "PUT",
                "/v1/workspaces/{workspace_id}/genai/prompts/{prompt_id}/{version}",
                "prompt",
                self.put_prompt,
            ),
            ("GET", "/v1/workspaces/{workspace_id}/genai/indexes", "indexes", self.indexes),
            (
                "GET",
                "/v1/workspaces/{workspace_id}/genai/indexes/{index_id}",
                "index",
                self.get_index,
            ),
            (
                "DELETE",
                "/v1/workspaces/{workspace_id}/genai/indexes/{index_id}",
                "index.delete",
                self.delete_index,
            ),
            (
                "POST",
                "/v1/workspaces/{workspace_id}/genai/indexes/{index_id}/query",
                "index.query",
                self.search_index,
            ),
            (
                "POST",
                "/v1/workspaces/{workspace_id}/genai/indexes/{index_id}/build",
                "index.build",
                self.build_index,
            ),
            ("GET", "/v1/workspaces/{workspace_id}/genai/tools", "tools", self.tools),
            (
                "GET",
                "/v1/workspaces/{workspace_id}/genai/tools/{tool_id}",
                "tool",
                self.get_tool,
            ),
            (
                "PUT",
                "/v1/workspaces/{workspace_id}/genai/tools/{tool_id}",
                "tool.put",
                self.put_tool,
            ),
            (
                "DELETE",
                "/v1/workspaces/{workspace_id}/genai/tools/{tool_id}",
                "tool.delete",
                self.delete_tool,
            ),
            ("GET", "/v1/workspaces/{workspace_id}/genai/agents", "agents", self.agents),
            (
                "GET",
                "/v1/workspaces/{workspace_id}/genai/agents/{agent_id}",
                "agent",
                self.get_agent,
            ),
            (
                "POST",
                "/v1/workspaces/{workspace_id}/genai/agents/{agent_id}/runs",
                "agent.run",
                self.run_agent,
            ),
            (
                "PUT",
                "/v1/workspaces/{workspace_id}/genai/agents/{agent_id}",
                "agent.put",
                self.put_agent,
            ),
            (
                "DELETE",
                "/v1/workspaces/{workspace_id}/genai/agents/{agent_id}",
                "agent.delete",
                self.delete_agent,
            ),
            (
                "GET",
                "/v1/workspaces/{workspace_id}/genai/agents/{agent_id}/runs",
                "agent.runs",
                self.agent_runs,
            ),
            (
                "GET",
                "/v1/workspaces/{workspace_id}/genai/runs/{run_id}",
                "agent.run.get",
                self.get_agent_run,
            ),
            (
                "POST",
                "/v1/workspaces/{workspace_id}/genai/rag/evaluations",
                "rag.evaluation",
                self.evaluate_rag,
            ),
            (
                "GET",
                "/v1/workspaces/{workspace_id}/genai/rag/evaluations/{evaluation_id}",
                "rag.evaluation.get",
                self.get_rag_evaluation,
            ),
        ):
            surface_id = f"genai.{operation}.v1"
            permission = "genai:write" if method == "DELETE" or method == "PUT" else "genai:read"
            context.contributions.add_route(
                method, path, context.plugin_id, handler, permission=permission
            )
            context.contributions.add_surface(SurfaceContribution(
                id=surface_id, plugin_id=context.plugin_id, namespace="genai",
                command=operation, operation_id=surface_id, capability="genai.discovery",
                permission=permission, path=path, method=method,
                output_schema={"type": "object"},
            ))

    def startup(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def providers(self, *, workspace_id: str = "", **_kwargs: object) -> object:
        if self._service is None:
            return {"status": "not_configured", "items": []}
        try:
            return self._service.providers(workspace_id)
        except Exception:
            return {"status": "unavailable", "items": []}

    def health(self, *, workspace_id: str = "", **_kwargs: object) -> object:
        if self._service is None:
            return {"status": "not_configured", "provider": "unavailable"}
        try:
            return self._service.health(workspace_id)
        except Exception:
            return {"status": "unhealthy", "provider": "unavailable"}

    def prompts(self, *, workspace_id: str = "", **_kwargs: object) -> object:
        if self._service is None:
            return {"status": "not_configured", "items": []}
        try:
            return self._service.prompts(workspace_id)
        except Exception:
            return {"status": "unavailable", "items": []}

    def put_prompt(
        self,
        *,
        workspace_id: str = "",
        prompt_id: str = "",
        version: str = "",
        body: object | None = None,
        **_kwargs: object,
    ) -> object:
        if self._service is None:
            return {"status": "not_configured"}
        if not isinstance(body, dict):
            return {"error": {"code": "invalid_request"}}
        try:
            payload = dict(body)
            payload["id"] = prompt_id
            payload["version"] = version
            prompt = PromptAsset.from_json(json.dumps(payload))
            result = self._service.put_prompt(workspace_id, prompt)
            return result.to_payload() if isinstance(result, PromptAsset) else result
        except Exception as exc:
            return {"error": {"code": "invalid_prompt", "message": str(exc)}}

    def indexes(self, *, workspace_id: str = "", **_kwargs: object) -> object:
        if self._service is None:
            return {"status": "not_configured", "items": []}
        try:
            return self._service.indexes(workspace_id)
        except Exception:
            return {"status": "unavailable", "items": []}

    def get_index(
        self, *, workspace_id: str = "", index_id: str = "", **_kwargs: object
    ) -> object:
        if self._service is None:
            return {"status": "not_configured", "item": None}
        try:
            result = self._service.get_index(workspace_id, index_id)
            return {"item": result} if result is not None else {"item": None}
        except Exception:
            return {"status": "unavailable", "item": None}

    def delete_index(
        self, *, workspace_id: str = "", index_id: str = "", **_kwargs: object
    ) -> object:
        if self._service is None:
            return {"status": "not_configured", "deleted": False}
        try:
            return {"deleted": bool(self._service.delete_index(workspace_id, index_id))}
        except Exception:
            return {"status": "unavailable", "deleted": False}

    def search_index(
        self,
        *,
        workspace_id: str = "",
        index_id: str = "",
        body: object | None = None,
        **_kwargs: object,
    ) -> object:
        if self._service is None:
            return {"status": "not_configured", "items": []}
        if not isinstance(body, dict):
            return {"error": {"code": "invalid_request"}}
        try:
            query = body.get("query_vector")
            top_k = body.get("top_k", 5)
            if (
                not isinstance(query, list)
                or not query
                or not all(
                    isinstance(value, (int, float)) and not isinstance(value, bool)
                    for value in query
                )
                or not isinstance(top_k, int)
                or isinstance(top_k, bool)
                or not 1 <= top_k <= 100
            ):
                return {"error": {"code": "invalid_query"}}
            return self._service.search_index(
                workspace_id,
                index_id,
                {"query_vector": [float(value) for value in query], "top_k": top_k},
            )
        except Exception as exc:
            return {"error": {"code": "query_failed", "message": str(exc)}}

    def build_index(
        self,
        *,
        workspace_id: str = "",
        index_id: str = "",
        body: object | None = None,
        **_kwargs: object,
    ) -> object:
        if self._service is None:
            return {"status": "not_configured"}
        if not isinstance(body, dict):
            return {"error": {"code": "invalid_request"}}
        rows = body.get("rows")
        batch_size = body.get("batch_size", 128)
        if (
            not isinstance(rows, list)
            or not all(isinstance(row, dict) for row in rows)
            or not isinstance(batch_size, int)
            or isinstance(batch_size, bool)
            or not 1 <= batch_size <= 2048
        ):
            return {"error": {"code": "invalid_build"}}
        try:
            return self._service.build_index(
                workspace_id,
                index_id,
                {"rows": rows, "batch_size": batch_size},
            )
        except Exception as exc:
            return {"error": {"code": "build_failed", "message": str(exc)}}

    def tools(self, *, workspace_id: str = "", **_kwargs: object) -> object:
        if self._service is None:
            return {"status": "not_configured", "items": []}
        try:
            return self._service.tools(workspace_id)
        except Exception:
            return {"status": "unavailable", "items": []}

    def get_tool(
        self, *, workspace_id: str = "", tool_id: str = "", **_kwargs: object
    ) -> object:
        if self._service is None:
            return {"status": "not_configured", "item": None}
        try:
            result = self._service.get_tool(workspace_id, tool_id)
            return {"item": result} if result is not None else {"item": None}
        except Exception:
            return {"status": "unavailable", "item": None}

    def put_tool(
        self,
        *,
        workspace_id: str = "",
        tool_id: str = "",
        body: object | None = None,
        idempotency_key: str | None = None,
        **_kwargs: object,
    ) -> object:
        if self._service is None:
            return {"status": "not_configured"}
        if not isinstance(body, dict):
            return {"error": {"code": "invalid_request"}}
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            return {"error": {"code": "missing_idempotency_key"}}
        try:
            payload = dict(body)
            payload["id"] = tool_id
            tool = ToolContract.from_payload(payload)
            result = self._service.put_tool(workspace_id, tool, idempotency_key)
            return result.to_payload() if isinstance(result, ToolContract) else result
        except Exception as exc:
            return {"error": {"code": "invalid_tool", "message": str(exc)}}

    def delete_tool(
        self,
        *,
        workspace_id: str = "",
        tool_id: str = "",
        idempotency_key: str | None = None,
        **_kwargs: object,
    ) -> object:
        if self._service is None:
            return {"status": "not_configured", "deleted": False}
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            return {"error": {"code": "missing_idempotency_key"}}
        try:
            return {
                "deleted": bool(
                    self._service.delete_tool(workspace_id, tool_id, idempotency_key)
                )
            }
        except Exception:
            return {"status": "unavailable", "deleted": False}

    def agents(self, *, workspace_id: str = "", **_kwargs: object) -> object:
        if self._service is None:
            return {"status": "not_configured", "items": []}
        try:
            return self._service.agents(workspace_id)
        except Exception:
            return {"status": "unavailable", "items": []}

    def get_agent(
        self, *, workspace_id: str = "", agent_id: str = "", **_kwargs: object
    ) -> object:
        if self._service is None:
            return {"status": "not_configured", "item": None}
        try:
            result = self._service.get_agent(workspace_id, agent_id)
            return {"item": result} if isinstance(result, AgentDefinition) else {"item": result}
        except Exception:
            return {"status": "unavailable", "item": None}

    def run_agent(
        self,
        *,
        workspace_id: str = "",
        agent_id: str = "",
        body: object | None = None,
        **_kwargs: object,
    ) -> object:
        if self._service is None:
            return {"status": "not_configured"}
        if not isinstance(body, dict):
            return {"error": {"code": "invalid_request"}}
        input_value = body.get("input")
        run_id = body.get("run_id")
        timeout = body.get("timeout_seconds", 60)
        cancel_requested = body.get("cancel_requested", False)
        if (
            not isinstance(input_value, str)
            or not input_value.strip()
            or "\x00" in input_value
            or not isinstance(run_id, str)
            or not run_id.strip()
            or "\x00" in run_id
            or not isinstance(timeout, (int, float))
            or isinstance(timeout, bool)
            or not 0.1 <= timeout <= 3600
            or not isinstance(cancel_requested, bool)
        ):
            return {"error": {"code": "invalid_agent_run"}}
        if cancel_requested:
            return {"status": "cancelled", "steps": []}
        try:
            return self._service.run_agent(
                workspace_id,
                agent_id,
                {
                    "input": input_value,
                    "run_id": run_id,
                    "timeout_seconds": float(timeout),
                    "cancel_requested": False,
                },
            )
        except TimeoutError:
            return {"status": "timeout", "steps": []}
        except Exception as exc:
            return {"error": {"code": "agent_failed", "message": str(exc)}}

    def put_agent(
        self,
        *,
        workspace_id: str = "",
        agent_id: str = "",
        body: object | None = None,
        idempotency_key: str | None = None,
        **_kwargs: object,
    ) -> object:
        if self._service is None:
            return {"status": "not_configured"}
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            return {"error": {"code": "missing_idempotency_key"}}
        if not isinstance(body, dict):
            return {"error": {"code": "invalid_request"}}
        try:
            payload = dict(body)
            payload["id"] = agent_id
            agent = AgentDefinition.from_payload(payload)
            result = self._service.put_agent(workspace_id, agent, idempotency_key)
            return result.to_payload() if isinstance(result, AgentDefinition) else result
        except Exception as exc:
            return {"error": {"code": "invalid_agent", "message": str(exc)}}

    def delete_agent(
        self,
        *,
        workspace_id: str = "",
        agent_id: str = "",
        idempotency_key: str | None = None,
        **_kwargs: object,
    ) -> object:
        if self._service is None:
            return {"status": "not_configured", "deleted": False}
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            return {"error": {"code": "missing_idempotency_key"}}
        try:
            return {
                "deleted": bool(
                    self._service.delete_agent(workspace_id, agent_id, idempotency_key)
                )
            }
        except Exception:
            return {"status": "unavailable", "deleted": False}

    def agent_runs(
        self, *, workspace_id: str = "", agent_id: str = "", **_kwargs: object
    ) -> object:
        if self._service is None:
            return {"status": "not_configured", "items": []}
        try:
            return self._service.agent_runs(workspace_id, agent_id)
        except Exception:
            return {"status": "unavailable", "items": []}

    def get_agent_run(
        self, *, workspace_id: str = "", run_id: str = "", **_kwargs: object
    ) -> object:
        if self._service is None:
            return {"status": "not_configured", "item": None}
        try:
            result = self._service.get_agent_run(workspace_id, run_id)
            return {"item": result} if result is not None else {"item": None}
        except Exception:
            return {"status": "unavailable", "item": None}

    def evaluate_rag(
        self, *, workspace_id: str = "", body: object | None = None, **_kwargs: object
    ) -> object:
        if self._service is None:
            return {"status": "not_configured"}
        if not isinstance(body, dict):
            return {"error": {"code": "invalid_request"}}
        examples = body.get("examples")
        if (
            not isinstance(examples, list)
            or not examples
            or len(examples) > 1000
            or not all(isinstance(example, dict) for example in examples)
        ):
            return {"error": {"code": "invalid_evaluation"}}
        try:
            result = self._service.evaluate_rag(workspace_id, {"examples": examples})
            if isinstance(result, RAGEvaluationReport):
                payload = result.to_payload()
                payload["evidence_digest"] = result.evidence_digest()
                return payload
            return result
        except Exception as exc:
            return {"error": {"code": "evaluation_failed", "message": str(exc)}}

    def get_rag_evaluation(
        self, *, workspace_id: str = "", evaluation_id: str = "", **_kwargs: object
    ) -> object:
        if self._service is None:
            return {"status": "not_configured", "item": None}
        try:
            result = self._service.get_rag_evaluation(workspace_id, evaluation_id)
            return {"item": result} if result is not None else {"item": None}
        except Exception:
            return {"status": "unavailable", "item": None}


def factory() -> GenAIPlugin:
    return GenAIPlugin()
