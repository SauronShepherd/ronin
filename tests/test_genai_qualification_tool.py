from tools.genai_qualification import qualify_manifest


def test_genai_qualification_manifest_is_machine_readable_and_fail_closed() -> None:
    result = qualify_manifest(
        {
            "provider": {
                "id": "provider",
                "adapter": "openai-compatible",
                "endpoint": "https://llm.test/v1",
            },
            "models": [
                {"model_id": "chat", "capabilities": ["chat"]},
                {"model_id": "embed", "capabilities": ["embedding"]},
            ],
        }
    )
    assert result["schema"] == "ronin.genai-qualification/v1"
    assert result["status"] == "qualified"


def test_genai_qualification_manifest_rejects_insecure_provider() -> None:
    result = qualify_manifest(
        {
            "provider": {
                "id": "provider",
                "adapter": "openai-compatible",
                "endpoint": "http://llm.test",
            },
            "models": [{"model_id": "chat", "capabilities": ["chat"]}],
        }
    )
    assert result["status"] == "rejected"
