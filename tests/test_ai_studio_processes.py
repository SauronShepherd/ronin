import pytest
from studio_ai_studio.processes import ProcessPolicyError, ProcessProfile, ProcessSupervisor


def profile():
    return ProcessProfile(
        "C:/ronin/bin/llama-server", ("--host", "127.0.0.1"), "C:/ronin/models",
        frozenset({"C:/ronin/bin/llama-server"}), frozenset({"C:/ronin/models"}),
    )


def test_profile_rejects_non_allowlisted_executable():
    invalid = ProcessProfile(
        "C:/tmp/evil", (), "C:/ronin/models", frozenset(), frozenset({"C:/ronin/models"})
    )
    with pytest.raises(ProcessPolicyError, match="allowlisted"):
        invalid.validate()


def test_supervisor_uses_no_shell_and_stops_cleanly():
    calls = []

    class FakeChild:
        def terminate(self): calls.append("terminate")
        def kill(self): calls.append("kill")
        def wait(self, timeout=None):
            calls.append(("wait", timeout))
            return 0

    def launcher(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeChild()

    supervisor = ProcessSupervisor(launcher=launcher)
    supervisor.start(profile())
    supervisor.stop(grace_seconds=1)
    assert calls[0][1]["shell"] is False
    assert "terminate" in calls
