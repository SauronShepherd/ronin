from __future__ import annotations

import asyncio

import pytest

from studio_server.http import ServiceTimeoutError, _ServiceLoop


class _Service:
    async def aclose(self) -> None:
        return None


def test_service_loop_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        _ServiceLoop(_Service(), timeout_seconds=0)


def test_service_loop_cancels_timed_out_coroutine() -> None:
    loop = _ServiceLoop(_Service(), timeout_seconds=0.01)
    try:
        with pytest.raises(ServiceTimeoutError, match="timed out"):
            loop.call(asyncio.sleep(1))
    finally:
        loop.close()
