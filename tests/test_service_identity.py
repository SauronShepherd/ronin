import pytest
from studio_security import (
    PrincipalId,
    ServiceIdentityError,
    ServiceIdentityLifecycle,
    SqliteServiceIdentityStore,
)


def test_service_identity_rotation_disables_old(tmp_path):
    store = SqliteServiceIdentityStore(tmp_path / "security.sqlite3")
    transitions = []
    lifecycle = ServiceIdentityLifecycle(store, on_transition=transitions.append)
    lifecycle.create("worker-v1", display_name="Worker", issuer="issuer", subject="sub-v1")
    replacement = lifecycle.rotate("worker-v1", "worker-v2", subject="sub-v2")
    assert replacement.id.value == "worker-v2"
    assert not store.get_service_identity(PrincipalId("worker-v1")).active
    assert store.get_service_identity(PrincipalId("worker-v2")).active
    assert [item.action for item in transitions] == ["create", "create", "disable", "rotate"]


def test_service_identity_rejects_duplicate(tmp_path):
    store = SqliteServiceIdentityStore(tmp_path / "security.sqlite3")
    lifecycle = ServiceIdentityLifecycle(store)
    lifecycle.create("worker", display_name="Worker", issuer="issuer", subject="sub")
    with pytest.raises(ServiceIdentityError):
        lifecycle.create("worker", display_name="Worker", issuer="issuer", subject="sub")


def test_service_identity_store_rejects_operator_principals(tmp_path):
    from studio_security import Principal, PrincipalId

    store = SqliteServiceIdentityStore(tmp_path / "security.sqlite3")
    operator = Principal(PrincipalId("operator"), "user", "Operator", "local", "operator")
    with pytest.raises(ValueError, match="only service identities can be stored in Public v1"):
        store.put_service_identity(operator)


def test_service_identity_store_prevents_subject_rebinding(tmp_path):
    from studio_security import IdentityConflict

    store = SqliteServiceIdentityStore(tmp_path / "security.sqlite3")
    lifecycle = ServiceIdentityLifecycle(store)
    lifecycle.create("worker-v1", display_name="Worker", issuer="issuer", subject="sub")
    with pytest.raises(
        IdentityConflict, match="service issuer/subject belongs to another identity"
    ):
        lifecycle.create("worker-v2", display_name="Worker", issuer="issuer", subject="sub")
