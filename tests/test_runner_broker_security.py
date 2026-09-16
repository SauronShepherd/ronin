from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from studio_core.canonical_json import encode as encode_canonical_json
from studio_kernel import (
    CancellationToken,
    CellExecutionRequest,
    CellExecutionResult,
    ExecutionAttemptId,
    KernelDirective,
)
from studio_notebook import CellId
from studio_runner_broker import RunnerBrokerConfig, RunnerBrokerServer
from studio_runners import (
    BrokerClient,
    BrokerContainerKernelExecutor,
    BrokerExecutorConfig,
    BrokerProtocolError,
)

_IMAGE = "sha256:" + "a" * 64
_OTHER_IMAGE = "sha256:" + "b" * 64
_TOKEN = "broker-test-token"  # noqa: S105 - deterministic fixture credential


class _FakeBrokerServer(RunnerBrokerServer):
    def __init__(self, *args, **kwargs):
        self.started = threading.Event()
        self.cancelled = threading.Event()
        self.execute_count = 0
        super().__init__(*args, **kwargs)

    async def execute(self, attempt_id, cell, cancellation):
        del attempt_id
        self.execute_count += 1
        self.started.set()
        while not cancellation.is_cancelled:  # noqa: ASYNC110 - polls cancellation signal
            await asyncio.sleep(0.01)
        self.cancelled.set()
        return CellExecutionResult(cell.cell_id, "cancelled")


class _PayloadClient(BrokerClient):
    def __init__(self, config: BrokerExecutorConfig, payload: dict[str, object]) -> None:
        super().__init__(config)
        object.__setattr__(self, "_payload", payload)

    def _request(self, method: str, path: str, payload: object | None = None) -> dict[str, object]:
        del method, path, payload
        return self._payload  # type: ignore[attr-defined]


def _config(tmp_path: Path) -> RunnerBrokerConfig:
    return RunnerBrokerConfig(_TOKEN, _IMAGE, tmp_path / "evidence")


def _start(tmp_path: Path):
    server = _FakeBrokerServer(("127.0.0.1", 0), _config(tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _client_config(server: RunnerBrokerServer, *, image: str = _IMAGE) -> BrokerExecutorConfig:
    return BrokerExecutorConfig(
        f"http://127.0.0.1:{server.server_port}",
        _TOKEN,
        image,
        allow_insecure_http=True,
        request_timeout_seconds=2.0,
        cancellation_poll_seconds=0.01,
    )


def _offline_client_config() -> BrokerExecutorConfig:
    return BrokerExecutorConfig(
        "http://runner-broker:8090",
        _TOKEN,
        _IMAGE,
        allow_insecure_http=True,
    )


def _cell() -> CellExecutionRequest:
    return CellExecutionRequest(
        CellId("cell-1"),
        "print('ok')",
        "print('ok')",
        "python",
        (),
        KernelDirective("python", "cell"),
    )


def _close(server: RunnerBrokerServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2.0)
    assert not thread.is_alive()


def test_broker_parser_rejects_docker_control_fields() -> None:
    base = {
        "version": 1,
        "attempt_id": "attempt-1",
        "cell": {
            "cell_id": "cell-1",
            "language": "python",
            "executable_source": "print('ok')",
        },
    }
    for field, value in (
        ("image", "evil:latest"),
        ("args", ["docker", "run", "--privileged"]),
        ("mounts", ["/:/host"]),
        ("network", "host"),
        ("capabilities", ["ALL"]),
    ):
        payload = dict(base)
        payload[field] = value
        with pytest.raises(ValueError, match="fields"):
            RunnerBrokerServer.parse_execution(payload)


def test_runtime_endpoint_requires_token_and_client_checks_image(tmp_path: Path) -> None:
    server, thread = _start(tmp_path)
    try:
        with pytest.raises(HTTPError) as unauthorized:
            urlopen(f"http://127.0.0.1:{server.server_port}/v1/runtime", timeout=1.0)  # noqa: S310
        assert unauthorized.value.code == 401

        client = BrokerClient(_client_config(server))
        assert client.runtime_image() == _IMAGE
        mismatched = BrokerClient(_client_config(server, image=_OTHER_IMAGE))
        with pytest.raises(BrokerProtocolError, match="does not match"):
            mismatched.runtime_image()
    finally:
        _close(server, thread)


def test_broker_executor_maps_kernel_cancellation_to_delete(tmp_path: Path) -> None:
    server, thread = _start(tmp_path)

    async def scenario() -> None:
        cancellation = CancellationToken()
        executor = BrokerContainerKernelExecutor(
            _client_config(server),
            ExecutionAttemptId("attempt-1"),
        )
        execution = asyncio.create_task(executor.execute(_cell(), cancellation))
        assert await asyncio.to_thread(server.started.wait, 1.0)
        cancellation.cancel()
        result = await asyncio.wait_for(execution, timeout=2.0)
        assert result.state == "cancelled"
        assert server.cancelled.is_set()
        assert server.execute_count == 1

    try:
        asyncio.run(scenario())
    finally:
        _close(server, thread)


def test_duplicate_active_execution_id_is_rejected(tmp_path: Path) -> None:
    server, thread = _start(tmp_path)
    try:
        token = server.begin_execution("exec-" + "1" * 32)
        assert token is not None
        assert server.begin_execution("exec-" + "1" * 32) is None
        assert server.cancel_execution("exec-" + "1" * 32)
        assert token.is_cancelled
        server.finish_execution("exec-" + "1" * 32, token)
        assert not server.cancel_execution("exec-" + "1" * 32)
    finally:
        _close(server, thread)


def test_execution_route_rejects_extra_request_fields_over_http(tmp_path: Path) -> None:
    server, thread = _start(tmp_path)
    payload = encode_canonical_json(
        {
            "version": 1,
            "attempt_id": "attempt-1",
            "cell": {
                "cell_id": "cell-1",
                "language": "python",
                "executable_source": "print('ok')",
            },
            "image": "evil:latest",
        }
    )
    request = Request(  # noqa: S310
        f"http://127.0.0.1:{server.server_port}/v1/executions/exec-{'2' * 32}",
        data=payload,
        headers={
            "Authorization": f"Bearer {_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with pytest.raises(HTTPError) as invalid:
            urlopen(request, timeout=1.0)  # noqa: S310
        assert invalid.value.code == 400
        assert server.execute_count == 0
    finally:
        _close(server, thread)


def test_client_rejects_invalid_execution_state() -> None:
    payload = {
        "version": 1,
        "cell_id": "cell-1",
        "state": "privileged",
        "failure_code": None,
        "evidence": [],
    }
    client = _PayloadClient(_offline_client_config(), payload)
    with pytest.raises(BrokerProtocolError, match="execution state"):
        client.execute("exec-" + "3" * 32, ExecutionAttemptId("attempt-1"), _cell())


def test_client_rejects_malformed_execution_evidence() -> None:
    payload = {
        "version": 1,
        "cell_id": "cell-1",
        "state": "succeeded",
        "failure_code": None,
        "evidence": [{"kind": "log", "ref": "local://log", "docker_args": ["--privileged"]}],
    }
    client = _PayloadClient(_offline_client_config(), payload)
    with pytest.raises(BrokerProtocolError, match="evidence item"):
        client.execute("exec-" + "4" * 32, ExecutionAttemptId("attempt-1"), _cell())


def test_broker_config_rejects_plaintext_without_explicit_opt_in() -> None:
    with pytest.raises(ValueError, match="explicit opt-in"):
        BrokerExecutorConfig("http://runner-broker:8090", _TOKEN, _IMAGE)
