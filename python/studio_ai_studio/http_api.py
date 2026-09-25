"""Host-neutral HTTP application adapter for AI Studio."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from .contracts import PublicModelName
from .errors import AIStudioError
from .gateway import BufferedGateway, Invocation
from .router import RouteCandidate


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    status: int
    body: Mapping[str, Any]


class AIStudioHTTPAPI:
    """Adapter used by Ronin's plugin router; it has no server-framework import."""

    def __init__(self, gateway: BufferedGateway, candidates: Sequence[RouteCandidate]) -> None:
        self._gateway = gateway
        self._candidates = tuple(candidates)

    def dispatch(
        self, method: str, path: str, body: Mapping[str, Any] | None = None
    ) -> HTTPResponse:
        try:
            if method == "GET" and path == "/v1/models":
                return HTTPResponse(
                    HTTPStatus.OK,
                    {
                        "object": "list",
                        "data": [
                            {"id": item.snapshot.public_name.value, "object": "model"}
                            for item in self._candidates
                        ],
                    },
                )
            if method == "POST" and path in {
                "/v1/chat/completions",
                "/v1/completions",
                "/v1/embeddings",
                "/v1/responses",
            }:
                if body is None:
                    return HTTPResponse(
                        HTTPStatus.BAD_REQUEST, {"error": {"code": "invalid_request"}}
                    )
                operation = {
                    "/v1/chat/completions": "chat",
                    "/v1/completions": "completion",
                    "/v1/embeddings": "embedding",
                    "/v1/responses": "response",
                }[path]
                model = body.get("model")
                if not isinstance(model, str):
                    return HTTPResponse(
                        HTTPStatus.BAD_REQUEST, {"error": {"code": "invalid_request"}}
                    )
                response = self._gateway.invoke(
                    Invocation("http-request", PublicModelName(model), operation, body),
                    self._candidates,
                )
                return HTTPResponse(HTTPStatus.OK, response)
            return HTTPResponse(HTTPStatus.NOT_FOUND, {"error": {"code": "not_found"}})
        except AIStudioError as exc:
            return HTTPResponse(exc.status, {"error": {"code": exc.code, "message": exc.message}})
