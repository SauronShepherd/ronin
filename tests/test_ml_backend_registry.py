import pytest

from studio_ml.backends import BackendRegistry, LocalScikitLearnBackend


def test_backend_registry_is_deterministic_and_rejects_duplicates() -> None:
    registry = BackendRegistry()
    first = LocalScikitLearnBackend()
    registry.register(first)
    assert registry.get(first.backend_id) is first
    assert [item.backend_id for item in registry.list()] == ["local.sklearn"]
    with pytest.raises(ValueError, match="already registered"):
        registry.register(LocalScikitLearnBackend())
