from studio_ai_studio.proxy import LocalModelEndpoint, LocalModelProxy, RoutingPolicy


def test_priority_routing_and_safe_forwarding():
    calls = []

    def transport(endpoint, path, payload, timeout):
        calls.append((endpoint.id, path, payload["model"], timeout))
        return 200, {"object": "chat.completion", "model": payload["model"]}

    proxy = LocalModelProxy(
        [
            LocalModelEndpoint("ollama", "http://127.0.0.1:11434", ("qwen",), priority=10),
            LocalModelEndpoint("vllm", "http://127.0.0.1:8000", ("qwen",), priority=20),
        ],
        transport=transport,
    )
    assert proxy.forward("/chat/completions", {"model": "qwen", "messages": []})[0] == 200
    assert calls == [("ollama", "/chat/completions", "qwen", 120.0)]


def test_round_robin_and_bounds():
    endpoints = [
        LocalModelEndpoint("a", "http://a.local", ("m",)),
        LocalModelEndpoint("b", "http://b.local", ("m",)),
    ]
    seen = []
    proxy = LocalModelProxy(
        endpoints,
        policy=RoutingPolicy(strategy="round_robin"),
        transport=lambda endpoint, *_: seen.append(endpoint.id) or (200, {}),
    )
    proxy.forward("/responses", {"model": "m"})
    proxy.forward("/responses", {"model": "m"})
    assert seen == ["a", "b"]
