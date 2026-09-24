"""Durable provider-neutral GenAI metadata persistence for Public v1."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, cast

from studio_core import AssetRef, WorkspaceId
from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json
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
from studio_core.grants import Requirement
from studio_orchestrator import Instant

from .catalog import CatalogAssetNotFound, migrate_catalog
from .sqlite import execute_migration_script, open_database
from .workspaces import WorkspaceNotFound

_GENAI_SCHEMA_VERSION = 3
_GENAI_MIGRATIONS = {1: "genai_001.sql", 2: "genai_002.sql", 3: "genai_003.sql"}


class GenAIConflict(RuntimeError):
    """Raised when a GenAI identity conflicts with durable state."""


def _agent_run_payload(
    run_id: str, agent_id: str, status: str, evidence: Mapping[str, object]
) -> dict[str, object]:
    if not run_id.strip() or not agent_id.strip() or not status.strip():
        raise ValueError("agent run identity and status are required")
    if "answer" in evidence or "prompt" in evidence or "input" in evidence:
        raise ValueError("agent run evidence must not contain model content")
    return {
        "run_id": run_id,
        "agent_id": agent_id,
        "status": status,
        "evidence": dict(evidence),
    }


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    execute_migration_script(connection, script)


def migrate_genai(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    now = Instant(now)
    migrate_catalog(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS genai_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM genai_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _GENAI_SCHEMA_VERSION:
        raise RuntimeError(
            f"GenAI schema {current} is newer than supported {_GENAI_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _GENAI_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_GENAI_MIGRATIONS[version]).read_text(encoding="utf-8")
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO genai_schema_migrations(version,applied_at) VALUES (?,?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def genai_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM genai_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


def _provider_json(provider: ModelProvider) -> str:
    return encode_canonical_json(provider.to_payload()).decode("utf-8")


def _provider_from_json(payload: str) -> ModelProvider:
    value = decode_canonical_json(payload)
    required = {"id", "adapter", "endpoint", "secret_ref", "properties"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("provider payload has invalid shape")
    provider_id, adapter, endpoint, secret_ref, properties = (
        value["id"],
        value["adapter"],
        value["endpoint"],
        value["secret_ref"],
        value["properties"],
    )
    if not isinstance(provider_id, str) or not isinstance(adapter, str):
        raise ValueError("provider id/adapter must be strings")
    if endpoint is not None and not isinstance(endpoint, str):
        raise ValueError("provider endpoint must be string or null")
    if secret_ref is not None and not isinstance(secret_ref, str):
        raise ValueError("provider secret_ref must be string or null")
    if not isinstance(properties, Mapping) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in properties.items()
    ):
        raise ValueError("provider properties must be string object")
    return ModelProvider(
        ProviderId(provider_id),
        adapter,
        cast(str | None, endpoint),
        None if secret_ref is None else SecretRef(secret_ref),
        tuple(sorted(cast(Mapping[str, str], properties).items())),
    )


def _index_from_json(payload: str) -> VectorIndexDefinition:
    value = decode_canonical_json(payload)
    required = {
        "id",
        "source",
        "provider_id",
        "embedding_model_id",
        "text_fields",
        "metadata_fields",
        "chunk_size",
        "chunk_overlap",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("vector index payload has invalid shape")
    text_fields, metadata_fields = value["text_fields"], value["metadata_fields"]
    if not isinstance(text_fields, list) or not all(isinstance(v, str) for v in text_fields):
        raise ValueError("vector index text_fields must be strings")
    if not isinstance(metadata_fields, list) or not all(
        isinstance(v, str) for v in metadata_fields
    ):
        raise ValueError("vector index metadata_fields must be strings")
    identifier, provider_id, model_id = (
        value["id"],
        value["provider_id"],
        value["embedding_model_id"],
    )
    chunk_size, chunk_overlap = value["chunk_size"], value["chunk_overlap"]
    if not all(isinstance(v, str) for v in (identifier, provider_id, model_id)):
        raise ValueError("vector index identity/model fields must be strings")
    if (
        not isinstance(chunk_size, int)
        or isinstance(chunk_size, bool)
        or not isinstance(chunk_overlap, int)
        or isinstance(chunk_overlap, bool)
    ):
        raise ValueError("vector index chunk sizes must be integers")
    return VectorIndexDefinition(
        VectorIndexId(cast(str, identifier)),
        AssetRef.from_payload(value["source"]),
        ProviderId(cast(str, provider_id)),
        cast(str, model_id),
        tuple(cast(str, field) for field in text_fields),
        tuple(cast(str, field) for field in metadata_fields),
        chunk_size,
        chunk_overlap,
    )


def _tool_from_json(payload: str) -> ToolContract:
    value = decode_canonical_json(payload)
    required = {
        "id",
        "name",
        "input_schema_ref",
        "output_schema_ref",
        "requirements",
        "side_effect",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("tool payload has invalid shape")
    requirements = value["requirements"]
    if not isinstance(requirements, list):
        raise ValueError("tool requirements must be array")
    strings = [
        value[k] for k in ("id", "name", "input_schema_ref", "output_schema_ref", "side_effect")
    ]
    if not all(isinstance(v, str) for v in strings):
        raise ValueError("tool fields must be strings")
    return ToolContract(
        ToolId(cast(str, value["id"])),
        cast(str, value["name"]),
        cast(str, value["input_schema_ref"]),
        cast(str, value["output_schema_ref"]),
        tuple(Requirement.from_payload(item) for item in requirements),
        cast("Literal['none', 'idempotent', 'non_idempotent']", value["side_effect"]),
    )


def _agent_from_json(payload: str) -> AgentDefinition:
    value = decode_canonical_json(payload)
    required = {
        "id",
        "name",
        "provider_id",
        "model_id",
        "prompt_id",
        "prompt_version",
        "tool_ids",
        "max_steps",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("agent payload has invalid shape")
    tool_ids, max_steps = value["tool_ids"], value["max_steps"]
    if not isinstance(tool_ids, list) or not all(isinstance(v, str) for v in tool_ids):
        raise ValueError("agent tool_ids must be strings")
    if not isinstance(max_steps, int) or isinstance(max_steps, bool):
        raise ValueError("agent max_steps must be integer")
    string_keys = ("id", "name", "provider_id", "model_id", "prompt_id", "prompt_version")
    if not all(isinstance(value[k], str) for k in string_keys):
        raise ValueError("agent identity/model fields must be strings")
    return AgentDefinition(
        AgentId(cast(str, value["id"])),
        cast(str, value["name"]),
        ProviderId(cast(str, value["provider_id"])),
        cast(str, value["model_id"]),
        PromptId(cast(str, value["prompt_id"])),
        PromptVersion(cast(str, value["prompt_version"])),
        tuple(ToolId(cast(str, v)) for v in tool_ids),
        max_steps,
    )


class SqliteGenAIStore:
    """SQLite reference metadata store; provider calls and vector materialization are separate."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        self._path = path
        connection = open_database(path)
        try:
            migrate_genai(connection, now=migration_now)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    def _require_active_workspace(
        self, connection: sqlite3.Connection, workspace_id: WorkspaceId
    ) -> None:
        row = connection.execute(
            "SELECT archived_at FROM workspaces WHERE workspace_id=?", (str(workspace_id),)
        ).fetchone()
        if row is None:
            raise WorkspaceNotFound(str(workspace_id))
        if row["archived_at"] is not None:
            raise GenAIConflict("cannot mutate GenAI state in an archived workspace")

    def put_provider(
        self, workspace_id: WorkspaceId, provider: ModelProvider, *, now: Instant | str
    ) -> ModelProvider:
        now = Instant(now)
        payload = _provider_json(provider)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            row = connection.execute(
                "SELECT provider_json FROM genai_providers WHERE workspace_id=? AND provider_id=?",
                (str(workspace_id), str(provider.id)),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO genai_providers("
                    "workspace_id,provider_id,provider_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?)",
                    (str(workspace_id), str(provider.id), payload, now, now),
                )
            elif row["provider_json"] != payload:
                connection.execute(
                    "UPDATE genai_providers SET provider_json=?,updated_at=?, "
                    "row_version=row_version+1 WHERE workspace_id=? AND provider_id=?",
                    (payload, now, str(workspace_id), str(provider.id)),
                )
            connection.execute("COMMIT")
            return provider
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_provider(
        self, workspace_id: WorkspaceId, provider_id: ProviderId
    ) -> ModelProvider | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT provider_json FROM genai_providers WHERE workspace_id=? AND provider_id=?",
                (str(workspace_id), str(provider_id)),
            ).fetchone()
            return None if row is None else _provider_from_json(row["provider_json"])
        finally:
            connection.close()

    def list_providers(self, workspace_id: WorkspaceId) -> tuple[ModelProvider, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT provider_json FROM genai_providers WHERE workspace_id=? "
                "ORDER BY provider_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(_provider_from_json(row["provider_json"]) for row in rows)
        finally:
            connection.close()

    def put_prompt(
        self, workspace_id: WorkspaceId, prompt: PromptAsset, *, now: Instant | str
    ) -> PromptAsset:
        now = Instant(now)
        payload = prompt.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            row = connection.execute(
                "SELECT prompt_json FROM prompt_versions "
                "WHERE workspace_id=? AND prompt_id=? AND version=?",
                (str(workspace_id), str(prompt.id), str(prompt.version)),
            ).fetchone()
            if row is not None:
                if row["prompt_json"] == payload:
                    connection.execute("COMMIT")
                    return prompt
                raise GenAIConflict(f"prompt version already exists: {prompt.id}@{prompt.version}")
            connection.execute(
                "INSERT INTO prompt_versions("
                "workspace_id,prompt_id,version,prompt_json,created_at) VALUES (?,?,?,?,?)",
                (str(workspace_id), str(prompt.id), str(prompt.version), payload, now),
            )
            connection.execute("COMMIT")
            return prompt
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_prompt(
        self, workspace_id: WorkspaceId, prompt_id: PromptId, version: PromptVersion
    ) -> PromptAsset | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT prompt_json FROM prompt_versions "
                "WHERE workspace_id=? AND prompt_id=? AND version=?",
                (str(workspace_id), str(prompt_id), str(version)),
            ).fetchone()
            return None if row is None else PromptAsset.from_json(row["prompt_json"])
        finally:
            connection.close()

    def list_prompts(self, workspace_id: WorkspaceId) -> tuple[PromptAsset, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT prompt_json FROM prompt_versions WHERE workspace_id=? "
                "ORDER BY prompt_id, version",
                (str(workspace_id),),
            ).fetchall()
            return tuple(PromptAsset.from_json(row["prompt_json"]) for row in rows)
        finally:
            connection.close()

    def put_index(
        self, workspace_id: WorkspaceId, definition: VectorIndexDefinition, *, now: Instant | str
    ) -> VectorIndexDefinition:
        now = Instant(now)
        payload = encode_canonical_json(definition.to_payload()).decode("utf-8")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            source = connection.execute(
                "SELECT 1 FROM catalog_asset_revisions "
                "WHERE workspace_id=? AND asset_id=? AND version=?",
                (
                    str(workspace_id),
                    str(definition.source.asset_id),
                    str(definition.source.version),
                ),
            ).fetchone()
            if source is None:
                raise CatalogAssetNotFound(
                    f"{definition.source.asset_id}@{definition.source.version}"
                )
            provider = connection.execute(
                "SELECT 1 FROM genai_providers WHERE workspace_id=? AND provider_id=?",
                (str(workspace_id), str(definition.provider_id)),
            ).fetchone()
            if provider is None:
                raise KeyError(str(definition.provider_id))
            row = connection.execute(
                "SELECT definition_json FROM vector_indexes "
                "WHERE workspace_id=? AND vector_index_id=?",
                (str(workspace_id), str(definition.id)),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO vector_indexes("
                    "workspace_id,vector_index_id,definition_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?)",
                    (str(workspace_id), str(definition.id), payload, now, now),
                )
            elif row["definition_json"] != payload:
                connection.execute(
                    "UPDATE vector_indexes SET definition_json=?,updated_at=?, "
                    "row_version=row_version+1 WHERE workspace_id=? AND vector_index_id=?",
                    (payload, now, str(workspace_id), str(definition.id)),
                )
            connection.execute("COMMIT")
            return definition
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_index(
        self, workspace_id: WorkspaceId, index_id: VectorIndexId
    ) -> VectorIndexDefinition | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT definition_json FROM vector_indexes "
                "WHERE workspace_id=? AND vector_index_id=?",
                (str(workspace_id), str(index_id)),
            ).fetchone()
            return None if row is None else _index_from_json(row["definition_json"])
        finally:
            connection.close()

    def list_indexes(self, workspace_id: WorkspaceId) -> tuple[VectorIndexDefinition, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT definition_json FROM vector_indexes WHERE workspace_id=? "
                "ORDER BY vector_index_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(_index_from_json(row["definition_json"]) for row in rows)
        finally:
            connection.close()

    def delete_index(self, workspace_id: WorkspaceId, index_id: VectorIndexId) -> bool:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            cursor = connection.execute(
                "DELETE FROM vector_indexes WHERE workspace_id=? AND vector_index_id=?",
                (str(workspace_id), str(index_id)),
            )
            connection.execute("COMMIT")
            return cursor.rowcount == 1
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def put_tool(
        self, workspace_id: WorkspaceId, tool: ToolContract, *, now: Instant | str
    ) -> ToolContract:
        now = Instant(now)
        payload = encode_canonical_json(tool.to_payload()).decode("utf-8")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            row = connection.execute(
                "SELECT definition_json FROM genai_tools WHERE workspace_id=? AND tool_id=?",
                (str(workspace_id), str(tool.id)),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO genai_tools("
                    "workspace_id,tool_id,definition_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?)",
                    (str(workspace_id), str(tool.id), payload, now, now),
                )
            elif row["definition_json"] != payload:
                connection.execute(
                    "UPDATE genai_tools SET definition_json=?,updated_at=?, "
                    "row_version=row_version+1 WHERE workspace_id=? AND tool_id=?",
                    (payload, now, str(workspace_id), str(tool.id)),
                )
            connection.execute("COMMIT")
            return tool
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_tool(self, workspace_id: WorkspaceId, tool_id: ToolId) -> ToolContract | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT definition_json FROM genai_tools WHERE workspace_id=? AND tool_id=?",
                (str(workspace_id), str(tool_id)),
            ).fetchone()
            return None if row is None else _tool_from_json(row["definition_json"])
        finally:
            connection.close()

    def list_tools(self, workspace_id: WorkspaceId) -> tuple[ToolContract, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT definition_json FROM genai_tools WHERE workspace_id=? ORDER BY tool_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(_tool_from_json(row["definition_json"]) for row in rows)
        finally:
            connection.close()

    def delete_tool(self, workspace_id: WorkspaceId, tool_id: ToolId) -> bool:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            cursor = connection.execute(
                "DELETE FROM genai_tools WHERE workspace_id=? AND tool_id=?",
                (str(workspace_id), str(tool_id)),
            )
            connection.execute("COMMIT")
            return cursor.rowcount == 1
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def put_agent(
        self, workspace_id: WorkspaceId, agent: AgentDefinition, *, now: Instant | str
    ) -> AgentDefinition:
        now = Instant(now)
        payload = encode_canonical_json(agent.to_payload()).decode("utf-8")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            if (
                connection.execute(
                    "SELECT 1 FROM genai_providers WHERE workspace_id=? AND provider_id=?",
                    (str(workspace_id), str(agent.provider_id)),
                ).fetchone()
                is None
            ):
                raise KeyError(str(agent.provider_id))
            if (
                connection.execute(
                    "SELECT 1 FROM prompt_versions "
                    "WHERE workspace_id=? AND prompt_id=? AND version=?",
                    (str(workspace_id), str(agent.prompt_id), str(agent.prompt_version)),
                ).fetchone()
                is None
            ):
                raise KeyError(f"{agent.prompt_id}@{agent.prompt_version}")
            for tool_id in agent.tool_ids:
                if (
                    connection.execute(
                        "SELECT 1 FROM genai_tools WHERE workspace_id=? AND tool_id=?",
                        (str(workspace_id), str(tool_id)),
                    ).fetchone()
                    is None
                ):
                    raise KeyError(str(tool_id))
            row = connection.execute(
                "SELECT definition_json FROM genai_agents WHERE workspace_id=? AND agent_id=?",
                (str(workspace_id), str(agent.id)),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO genai_agents("
                    "workspace_id,agent_id,definition_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?)",
                    (str(workspace_id), str(agent.id), payload, now, now),
                )
            elif row["definition_json"] != payload:
                connection.execute(
                    "UPDATE genai_agents SET definition_json=?,updated_at=?, "
                    "row_version=row_version+1 WHERE workspace_id=? AND agent_id=?",
                    (payload, now, str(workspace_id), str(agent.id)),
                )
            connection.execute("COMMIT")
            return agent
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_agent(self, workspace_id: WorkspaceId, agent_id: AgentId) -> AgentDefinition | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT definition_json FROM genai_agents WHERE workspace_id=? AND agent_id=?",
                (str(workspace_id), str(agent_id)),
            ).fetchone()
            return None if row is None else _agent_from_json(row["definition_json"])
        finally:
            connection.close()

    def list_agents(self, workspace_id: WorkspaceId) -> tuple[AgentDefinition, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT definition_json FROM genai_agents WHERE workspace_id=? ORDER BY agent_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(_agent_from_json(row["definition_json"]) for row in rows)
        finally:
            connection.close()

    def delete_agent(self, workspace_id: WorkspaceId, agent_id: AgentId) -> bool:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            cursor = connection.execute(
                "DELETE FROM genai_agents WHERE workspace_id=? AND agent_id=?",
                (str(workspace_id), str(agent_id)),
            )
            connection.execute("COMMIT")
            return cursor.rowcount == 1
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def put_agent_run(
        self,
        workspace_id: WorkspaceId,
        run_id: str,
        agent_id: str,
        status: str,
        evidence: Mapping[str, object],
        *,
        now: Instant | str,
    ) -> dict[str, object]:
        payload = _agent_run_payload(run_id, agent_id, status, evidence)
        now = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            encoded = encode_canonical_json(payload["evidence"]).decode("utf-8")
            existing = connection.execute(
                "SELECT agent_id,status,evidence_json FROM genai_agent_runs "
                "WHERE workspace_id=? AND run_id=?",
                (str(workspace_id), run_id),
            ).fetchone()
            if existing is not None:
                if (
                    existing["agent_id"] != agent_id
                    or existing["status"] != status
                    or existing["evidence_json"] != encoded
                ):
                    raise GenAIConflict("agent run identity conflicts with durable state")
                connection.execute("COMMIT")
                return payload
            connection.execute(
                "INSERT INTO genai_agent_runs("
                "workspace_id,run_id,agent_id,status,evidence_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (str(workspace_id), run_id, agent_id, status, encoded, now, now),
            )
            connection.execute("COMMIT")
            return payload
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_agent_run(self, workspace_id: WorkspaceId, run_id: str) -> dict[str, object] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT run_id,agent_id,status,evidence_json FROM genai_agent_runs "
                "WHERE workspace_id=? AND run_id=?",
                (str(workspace_id), run_id),
            ).fetchone()
            if row is None:
                return None
            return {
                "run_id": row["run_id"],
                "agent_id": row["agent_id"],
                "status": row["status"],
                "evidence": decode_canonical_json(row["evidence_json"]),
            }
        finally:
            connection.close()

    def list_agent_runs(self, workspace_id: WorkspaceId) -> tuple[dict[str, object], ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT run_id,agent_id,status,evidence_json FROM genai_agent_runs "
                "WHERE workspace_id=? ORDER BY run_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(
                {
                    "run_id": row["run_id"],
                    "agent_id": row["agent_id"],
                    "status": row["status"],
                    "evidence": decode_canonical_json(row["evidence_json"]),
                }
                for row in rows
            )
        finally:
            connection.close()

    def put_rag_evaluation(
        self,
        workspace_id: WorkspaceId,
        evaluation_id: str,
        payload: Mapping[str, object],
        digest: str,
        *,
        now: Instant | str,
    ) -> dict[str, object]:
        if not evaluation_id.strip() or not digest.strip():
            raise ValueError("RAG evaluation identity and digest are required")
        encoded = encode_canonical_json(dict(payload)).decode("utf-8")
        now = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            existing = connection.execute(
                "SELECT payload_json,digest FROM genai_rag_evaluations "
                "WHERE workspace_id=? AND evaluation_id=?",
                (str(workspace_id), evaluation_id),
            ).fetchone()
            if existing is not None:
                if existing["payload_json"] != encoded or existing["digest"] != digest:
                    raise GenAIConflict("RAG evaluation identity conflicts with durable state")
                connection.execute("COMMIT")
                return {"evaluation_id": evaluation_id, "payload": dict(payload), "digest": digest}
            connection.execute(
                "INSERT INTO genai_rag_evaluations("
                "workspace_id,evaluation_id,payload_json,digest,created_at) "
                "VALUES (?,?,?,?,?)",
                (str(workspace_id), evaluation_id, encoded, digest, now),
            )
            connection.execute("COMMIT")
            return {"evaluation_id": evaluation_id, "payload": dict(payload), "digest": digest}
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_rag_evaluation(
        self, workspace_id: WorkspaceId, evaluation_id: str
    ) -> dict[str, object] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT payload_json,digest FROM genai_rag_evaluations "
                "WHERE workspace_id=? AND evaluation_id=?",
                (str(workspace_id), evaluation_id),
            ).fetchone()
            if row is None:
                return None
            return {
                "evaluation_id": evaluation_id,
                "payload": decode_canonical_json(row["payload_json"]),
                "digest": row["digest"],
            }
        finally:
            connection.close()
