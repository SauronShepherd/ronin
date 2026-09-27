from studio_security import (
    PrincipalId,
    ServiceIdentityError,
    ServiceIdentityLifecycle,
    SqliteIdentityStore,
)


def test_service_identity_rotation_disables_old(tmp_path):
    store = SqliteIdentityStore(tmp_path / "security.sqlite3")
    transitions = []
    lifecycle = ServiceIdentityLifecycle(store, on_transition=transitions.append)
    lifecycle.create("worker-v1", display_name="Worker", issuer="issuer", subject="sub-v1")
    replacement = lifecycle.rotate("worker-v1", "worker-v2", subject="sub-v2")
    assert replacement.id.value == "worker-v2"
    assert not store.get_principal(PrincipalId("worker-v1")).active
    assert store.get_principal(PrincipalId("worker-v2")).active
    assert [item.action for item in transitions] == ["create", "create", "disable", "rotate"]


def test_service_identity_rejects_duplicate(tmp_path):
    store = SqliteIdentityStore(tmp_path / "security.sqlite3")
    lifecycle = ServiceIdentityLifecycle(store)
    lifecycle.create("worker", display_name="Worker", issuer="issuer", subject="sub")
    try:
        lifecycle.create("worker", display_name="Worker", issuer="issuer", subject="sub")
    except ServiceIdentityError:
        pass
    else:
        raise AssertionError("duplicate service identity was accepted")
