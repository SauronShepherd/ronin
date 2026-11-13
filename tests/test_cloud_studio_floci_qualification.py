from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import tools.cloud_studio_floci_qualification as qualification
from tools.cloud_studio_floci_qualification import qualify


class FakeBackend:
    def __init__(self, *, residual: str = "", apply_error: bool = False) -> None:
        self.residual = residual
        self.apply_error = apply_error
        self.calls: list[str] = []

    def health(self) -> dict[str, object]:
        self.calls.append("health")
        return {"available": True}

    def plan(self, _topology) -> dict[str, object]:
        self.calls.append("plan")
        return {"returncode": 0, "stdout": "Plan: 2 to add."}

    def apply(self, _topology) -> dict[str, object]:
        self.calls.append("apply")
        if self.apply_error:
            raise RuntimeError("simulated apply failure")
        return {"returncode": 0, "stdout": "Apply complete!"}

    def refresh(self) -> dict[str, object]:
        self.calls.append("refresh")
        return {"returncode": 0, "stdout": "Refresh complete."}

    def destroy(self) -> dict[str, object]:
        self.calls.append("destroy")
        return {"returncode": 0, "stdout": "Destroy complete!"}

    def state_list(self) -> dict[str, object]:
        self.calls.append("state_list")
        return {"returncode": 0, "stdout": self.residual}


class FlociFakeBackend(FakeBackend):
    name = "floci"
    endpoint = "http://127.0.0.1:4566"


class TimeoutBackend(FakeBackend):
    command_timeout_seconds = 120.0


def test_floci_qualification_never_passes_without_terraform() -> None:
    backend = FakeBackend()

    result = qualify("http://127.0.0.1:4566", ".tmp/floci", backend=backend)

    assert result["status"] == "blocked"
    assert "no PASS" in result["reason"]
    assert backend.calls == ["health"]


def test_qualification_creates_new_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "nested" / "cloud"
    result = qualify("http://127.0.0.1:4566", str(workspace), backend=FakeBackend())

    assert result["status"] == "blocked"
    assert workspace.is_dir()


def test_qualification_can_select_backend_and_command_timeout() -> None:
    backend = TimeoutBackend()
    result = qualify(
        "http://127.0.0.1:4566",
        ".tmp/localstack",
        terraform=False,
        backend=backend,
        backend_kind="localstack",
        command_timeout_seconds=300,
    )
    assert result["backend"] == "localstack"
    assert result["status"] == "blocked"
    assert backend.command_timeout_seconds == 300


def test_floci_terraform_qualification_rejects_non_loopback_before_health_check() -> None:
    backend = FakeBackend()

    result = qualify("https://cloud.example.test", ".tmp/floci", terraform=True, backend=backend)

    assert result["status"] == "failed"
    assert backend.calls == []
    assert any("loopback" in error for error in result["errors"])


def test_floci_qualification_requires_all_terraform_stages_and_empty_state() -> None:
    backend = FakeBackend()

    result = qualify("http://127.0.0.1:4566", ".tmp/floci", terraform=True, backend=backend)

    assert result["status"] == "passed"
    assert result["residual_resources"] == []
    assert backend.calls == ["health", "plan", "apply", "refresh", "destroy", "state_list"]
    assert result["terraform_versions"] == {"terraform": "1.13.5", "aws_provider": "6.65.0"}


def test_floci_qualification_checks_applied_resources_and_removal(monkeypatch) -> None:
    backend = FlociFakeBackend()
    observed = iter(
        [
            ["s3://qualification-bucket", "sqs://qualification-queue"],
            [],
        ]
    )
    monkeypatch.setattr(
        qualification, "_list_floci_fixture_resources", lambda _endpoint: next(observed)
    )

    result = qualify(backend.endpoint, ".tmp/floci", terraform=True, backend=backend)

    assert result["status"] == "passed"
    assert result["floci_fixture_resources_after_apply"] == [
        "s3://qualification-bucket",
        "sqs://qualification-queue",
    ]
    assert result["floci_fixture_residual_resources"] == []
    assert backend.calls == ["health", "plan", "apply", "refresh", "destroy", "state_list"]


def test_floci_qualification_fails_if_fixture_resources_survive_destroy(monkeypatch) -> None:
    backend = FlociFakeBackend()
    observed = iter(
        [
            ["s3://qualification-bucket", "sqs://qualification-queue"],
            ["s3://qualification-bucket"],
        ]
    )
    monkeypatch.setattr(
        qualification, "_list_floci_fixture_resources", lambda _endpoint: next(observed)
    )

    result = qualify(backend.endpoint, ".tmp/floci", terraform=True, backend=backend)

    assert result["status"] == "failed"
    assert result["floci_fixture_residual_resources"] == ["s3://qualification-bucket"]
    assert any("resources remain after destroy" in error for error in result["errors"])
    assert backend.calls[-2:] == ["destroy", "state_list"]


def test_floci_qualification_fails_if_apply_does_not_create_fixture(monkeypatch) -> None:
    backend = FlociFakeBackend()
    observed = iter([[], []])
    monkeypatch.setattr(
        qualification, "_list_floci_fixture_resources", lambda _endpoint: next(observed)
    )

    result = qualify(backend.endpoint, ".tmp/floci", terraform=True, backend=backend)

    assert result["status"] == "failed"
    assert any("did not expose the applied fixture" in error for error in result["errors"])
    assert backend.calls[-2:] == ["destroy", "state_list"]


def test_floci_qualification_verifies_selected_terraform_binary(monkeypatch) -> None:
    backend = FakeBackend()
    backend.terraform_executable = "terraform-test-double"
    monkeypatch.setattr(
        qualification.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"terraform_version": "1.16.2"}),
        ),
    )

    result = qualify("http://127.0.0.1:4566", ".tmp/floci", terraform=True, backend=backend)

    assert result["status"] == "failed"
    assert any("1.13.5 is required" in error for error in result["errors"])
    assert backend.calls == ["health"]


def test_floci_qualification_fails_when_destroy_leaves_resources() -> None:
    backend = FakeBackend(residual="aws_s3_bucket.qualification")

    result = qualify("http://127.0.0.1:4566", ".tmp/floci", terraform=True, backend=backend)

    assert result["status"] == "failed"
    assert result["residual_resources"] == ["aws_s3_bucket.qualification"]
    assert any("not empty after destroy" in error for error in result["errors"])


def test_floci_qualification_attempts_cleanup_after_apply_failure() -> None:
    backend = FakeBackend(apply_error=True)

    result = qualify("http://127.0.0.1:4566", ".tmp/floci", terraform=True, backend=backend)

    assert result["status"] == "failed"
    assert backend.calls[-2:] == ["destroy", "state_list"]
    assert any("simulated apply failure" in error for error in result["errors"])


def test_floci_qualification_rejects_nonzero_terraform_command() -> None:
    backend = FakeBackend()

    def bad_plan(_topology) -> dict[str, object]:
        backend.calls.append("plan")
        return {"returncode": 1, "stderr": "invalid provider"}

    backend.plan = bad_plan
    result = qualify("http://127.0.0.1:4566", ".tmp/floci", terraform=True, backend=backend)

    assert result["status"] == "failed"
    assert backend.calls == ["health", "plan"]


def test_floci_compose_is_version_pinned_and_loopback_only() -> None:
    root = Path(__file__).resolve().parents[1]
    compose = (root / "examples/cloud-studio/compose.floci.yaml").read_text(encoding="utf-8")

    assert (
        "image: floci/floci:2.1.0@sha256:"
        "f5aa8c18302cedb4f2385f5c4e455b3efc77fee6bf7b6e5d1712b2817ba102db" in compose
    )
    assert '"127.0.0.1:${RONIN_FLOCI_PORT:-4566}:4566"' in compose
