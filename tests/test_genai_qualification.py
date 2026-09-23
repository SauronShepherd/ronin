from studio_core.genai import GenAIModel, ModelProvider, ProviderId
from studio_genai import qualify_provider_model


def test_openai_compatible_provider_model_qualifies() -> None:
    provider = ModelProvider(ProviderId("provider"), "openai-compatible", "https://llm.test/v1")
    model = GenAIModel(provider.id, "chat", frozenset({"chat"}))
    result = qualify_provider_model(provider, model)
    assert result.status == "qualified"
    assert result.to_payload()["capabilities"] == ["chat"]


def test_provider_qualification_rejects_mismatch_and_insecure_endpoint() -> None:
    provider = ModelProvider(ProviderId("provider"), "openai-compatible", "http://llm.test/v1")
    model = GenAIModel(ProviderId("other"), "chat", frozenset({"chat"}))
    result = qualify_provider_model(provider, model)
    assert result.status == "rejected"
    assert set(result.findings) == {"model_provider_mismatch", "provider_endpoint_not_secure"}
