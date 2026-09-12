"""Provider-neutral GenAI, RAG, and agent contracts for Ronin Public v1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json
from .catalog import AssetRef
from .connections import SecretRef
from .grants import Requirement

ModelCapability: TypeAlias = Literal["chat", "embedding", "tool_use", "structured_output"]
ToolSideEffect: TypeAlias = Literal["none", "idempotent", "non_idempotent"]


def _text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


def _pairs(values: tuple[tuple[str, str], ...], name: str) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value in values:
        key = _text(key, f"{name} key")
        value = _text(value, f"{name} value")
        if any(term in key.casefold() for term in ("password", "secret", "token", "credential", "api_key")):
            raise ValueError(f"{name} must not contain credential-bearing keys")
        if key in seen: raise ValueError(f"{name} keys must be unique")
        seen.add(key); result.append((key,value))
    return tuple(sorted(result))


@dataclass(frozen=True, order=True, slots=True)
class ProviderId:
    value: str
    def __post_init__(self) -> None: _text(self.value, "provider id")
    def __str__(self) -> str: return self.value


@dataclass(frozen=True, order=True, slots=True)
class PromptId:
    value: str
    def __post_init__(self) -> None: _text(self.value, "prompt id")
    def __str__(self) -> str: return self.value


@dataclass(frozen=True, order=True, slots=True)
class PromptVersion:
    value: str
    def __post_init__(self) -> None: _text(self.value, "prompt version")
    def __str__(self) -> str: return self.value


@dataclass(frozen=True, order=True, slots=True)
class VectorIndexId:
    value: str
    def __post_init__(self) -> None: _text(self.value, "vector index id")
    def __str__(self) -> str: return self.value


@dataclass(frozen=True, order=True, slots=True)
class ToolId:
    value: str
    def __post_init__(self) -> None: _text(self.value, "tool id")
    def __str__(self) -> str: return self.value


@dataclass(frozen=True, order=True, slots=True)
class AgentId:
    value: str
    def __post_init__(self) -> None: _text(self.value, "agent id")
    def __str__(self) -> str: return self.value


@dataclass(frozen=True, slots=True)
class ModelProvider:
    id: ProviderId
    adapter: str
    endpoint: str | None = None
    secret_ref: SecretRef | None = None
    properties: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _text(self.adapter, "provider adapter")
        if self.endpoint is not None: _text(self.endpoint, "provider endpoint")
        object.__setattr__(self, "properties", _pairs(self.properties, "provider properties"))

    def to_payload(self) -> dict[str, object]:
        return {"id":self.id.value,"adapter":self.adapter,"endpoint":self.endpoint,"secret_ref":None if self.secret_ref is None else self.secret_ref.uri,"properties":dict(self.properties)}


@dataclass(frozen=True, slots=True)
class GenAIModel:
    provider_id: ProviderId
    model_id: str
    capabilities: frozenset[ModelCapability]
    context_limit: int | None = None

    def __post_init__(self) -> None:
        _text(self.model_id, "GenAI model id")
        allowed={"chat","embedding","tool_use","structured_output"}
        if not self.capabilities or not self.capabilities.issubset(allowed): raise ValueError("unsupported/empty GenAI capabilities")
        if self.context_limit is not None and self.context_limit < 1: raise ValueError("context_limit must be positive")

    def to_payload(self) -> dict[str, object]:
        return {"provider_id":self.provider_id.value,"model_id":self.model_id,"capabilities":sorted(self.capabilities),"context_limit":self.context_limit}


@dataclass(frozen=True, slots=True)
class PromptAsset:
    id: PromptId
    version: PromptVersion
    template: str
    parameter_names: tuple[str, ...] = ()
    required_capabilities: frozenset[ModelCapability] = frozenset({"chat"})

    def __post_init__(self) -> None:
        if not self.template or "\x00" in self.template: raise ValueError("prompt template must be non-empty")
        parameters=tuple(sorted(_text(v,"prompt parameter") for v in self.parameter_names))
        if len(parameters)!=len(set(parameters)): raise ValueError("prompt parameters must be unique")
        allowed={"chat","embedding","tool_use","structured_output"}
        if not self.required_capabilities.issubset(allowed): raise ValueError("unsupported prompt capability")
        object.__setattr__(self,"parameter_names",parameters)

    def to_payload(self) -> dict[str, object]:
        return {"id":self.id.value,"version":self.version.value,"template":self.template,"parameter_names":list(self.parameter_names),"required_capabilities":sorted(self.required_capabilities)}

    def to_json(self) -> str: return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_json(cls,payload:str)->PromptAsset:
        value=decode_canonical_json(payload)
        if not isinstance(value,Mapping) or set(value)!={"id","version","template","parameter_names","required_capabilities"}: raise ValueError("prompt has invalid shape")
        if not all(isinstance(value[k],str) for k in ("id","version","template")): raise ValueError("prompt identity/template fields must be strings")
        params=value["parameter_names"]; caps=value["required_capabilities"]
        if not isinstance(params,list) or not all(isinstance(v,str) for v in params) or not isinstance(caps,list) or not all(isinstance(v,str) for v in caps): raise ValueError("prompt arrays invalid")
        return cls(PromptId(cast(str,value["id"])),PromptVersion(cast(str,value["version"])),cast(str,value["template"]),tuple(params),frozenset(cast(list[ModelCapability],caps)))


@dataclass(frozen=True, slots=True)
class VectorIndexDefinition:
    id: VectorIndexId
    source: AssetRef
    provider_id: ProviderId
    embedding_model_id: str
    text_fields: tuple[str, ...]
    metadata_fields: tuple[str, ...] = ()
    chunk_size: int = 1000
    chunk_overlap: int = 100

    def __post_init__(self) -> None:
        _text(self.embedding_model_id,"embedding model id")
        text_fields=tuple(sorted(_text(v,"vector text field") for v in self.text_fields))
        metadata_fields=tuple(sorted(_text(v,"vector metadata field") for v in self.metadata_fields))
        if not text_fields: raise ValueError("vector index requires text_fields")
        if len(text_fields)!=len(set(text_fields)) or len(metadata_fields)!=len(set(metadata_fields)): raise ValueError("vector index fields must be unique")
        if self.chunk_size < 1 or self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size: raise ValueError("invalid vector chunk sizing")
        object.__setattr__(self,"text_fields",text_fields); object.__setattr__(self,"metadata_fields",metadata_fields)

    def to_payload(self)->dict[str,object]:
        return {"id":self.id.value,"source":self.source.to_payload(),"provider_id":self.provider_id.value,"embedding_model_id":self.embedding_model_id,"text_fields":list(self.text_fields),"metadata_fields":list(self.metadata_fields),"chunk_size":self.chunk_size,"chunk_overlap":self.chunk_overlap}


@dataclass(frozen=True, slots=True)
class RAGDefinition:
    name: str
    index_id: VectorIndexId
    prompt_id: PromptId
    prompt_version: PromptVersion
    provider_id: ProviderId
    model_id: str
    top_k: int = 5

    def __post_init__(self)->None:
        _text(self.name,"RAG name"); _text(self.model_id,"RAG model id")
        if self.top_k < 1 or self.top_k > 100: raise ValueError("RAG top_k must be between 1 and 100")

    def to_payload(self)->dict[str,object]:
        return {"name":self.name,"index_id":self.index_id.value,"prompt_id":self.prompt_id.value,"prompt_version":self.prompt_version.value,"provider_id":self.provider_id.value,"model_id":self.model_id,"top_k":self.top_k}


@dataclass(frozen=True, slots=True)
class ToolContract:
    id: ToolId
    name: str
    input_schema_ref: str
    output_schema_ref: str
    requirements: tuple[Requirement, ...] = ()
    side_effect: ToolSideEffect = "none"

    def __post_init__(self)->None:
        _text(self.name,"tool name"); _text(self.input_schema_ref,"tool input schema ref"); _text(self.output_schema_ref,"tool output schema ref")
        if self.side_effect not in {"none","idempotent","non_idempotent"}: raise ValueError("unsupported tool side_effect")
        requirements=tuple(sorted(self.requirements,key=lambda item:item.canonical_key))
        if len(requirements)!=len(set(item.canonical_key for item in requirements)): raise ValueError("tool requirements must be unique")
        object.__setattr__(self,"requirements",requirements)

    def to_payload(self)->dict[str,object]:
        return {"id":self.id.value,"name":self.name,"input_schema_ref":self.input_schema_ref,"output_schema_ref":self.output_schema_ref,"requirements":[r.to_payload() for r in self.requirements],"side_effect":self.side_effect}


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    id: AgentId
    name: str
    provider_id: ProviderId
    model_id: str
    prompt_id: PromptId
    prompt_version: PromptVersion
    tool_ids: tuple[ToolId, ...] = ()
    max_steps: int = 8

    def __post_init__(self)->None:
        _text(self.name,"agent name"); _text(self.model_id,"agent model id")
        tools=tuple(sorted(set(self.tool_ids)))
        if self.max_steps < 1 or self.max_steps > 128: raise ValueError("agent max_steps must be between 1 and 128")
        object.__setattr__(self,"tool_ids",tools)

    def to_payload(self)->dict[str,object]:
        return {"id":self.id.value,"name":self.name,"provider_id":self.provider_id.value,"model_id":self.model_id,"prompt_id":self.prompt_id.value,"prompt_version":self.prompt_version.value,"tool_ids":[tool.value for tool in self.tool_ids],"max_steps":self.max_steps}
