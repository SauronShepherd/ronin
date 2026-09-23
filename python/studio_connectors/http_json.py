"""Bounded HTTP JSON connector with deployment-local secret resolution."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, urlsplit

from studio_core import (
    AssetHandle,
    ConnectionDefinition,
    ConnectorCapabilities,
    ConnectorDescriptor,
    DiscoveredAsset,
    FieldSchema,
    SecretRef,
    SourceCheckpoint,
)
from studio_storage.secrets import SecretResolver

from .contracts import ConnectorReadResult


class HttpConnectorDependencyError(RuntimeError):
    """Raised when the optional HTTP client dependency is unavailable."""


def _httpx() -> Any:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise HttpConnectorDependencyError(
            "HTTP connector support requires the optional Ronin data-plane dependencies"
        ) from exc
    return httpx


def _options(connection: ConnectionDefinition) -> dict[str, str]:
    return dict(connection.options)


def _secret_refs(connection: ConnectionDefinition) -> dict[str, SecretRef]:
    return dict(connection.secret_refs)


def _type_name(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def _infer_fields(rows: tuple[dict[str, object], ...]) -> tuple[FieldSchema, ...]:
    if not rows:
        return ()
    names = tuple(sorted(rows[0]))
    expected = set(names)
    for row in rows:
        if set(row) != expected:
            raise ValueError("HTTP JSON records must have a consistent object shape")
    fields: list[FieldSchema] = []
    for name in names:
        values = [row[name] for row in rows]
        non_null = [value for value in values if value is not None]
        types = sorted({_type_name(value) for value in non_null})
        type_name = types[0] if len(types) == 1 else "json"
        fields.append(FieldSchema(name, type_name, any(value is None for value in values)))
    return tuple(fields)


def _validate_endpoint_host(hostname: str, *, allow_private: bool) -> None:
    """Reject DNS/IP targets that can turn a connector into an SSRF primitive."""
    if allow_private:
        return
    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(info[4][0])
                for info in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
            }
        except OSError as exc:
            raise ValueError("HTTP base_url hostname could not be resolved safely") from exc
    if not addresses or any(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
        for address in addresses
    ):
        raise ValueError("HTTP base_url resolves to a private or reserved network")


class HttpJsonConnector:
    """Read bounded JSON records from one base URL without implicit redirect trust."""

    descriptor = ConnectorDescriptor(
        "http.json",
        1,
        ConnectorCapabilities(read=True),
    )

    def _validate(self, connection: ConnectionDefinition) -> tuple[str, dict[str, str]]:
        if connection.connector_id != self.descriptor.connector_id:
            raise ValueError("connection does not target the HTTP JSON connector")
        options = _options(connection)
        base_url = options.get("base_url")
        if base_url is None:
            raise ValueError("HTTP connection requires base_url")
        parsed = urlsplit(base_url)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("HTTP base_url must not embed credentials")
        allow_http = options.get("allow_http", "false").casefold() == "true"
        if parsed.scheme not in ({"https", "http"} if allow_http else {"https"}):
            raise ValueError("HTTP base_url must use HTTPS unless allow_http=true")
        if not parsed.hostname:
            raise ValueError("HTTP base_url requires a hostname")
        if parsed.query or parsed.fragment:
            raise ValueError("HTTP base_url must not contain query or fragment components")
        return base_url.rstrip("/"), options

    def discover(
        self,
        connection: ConnectionDefinition,
        secrets: SecretResolver,
    ) -> tuple[DiscoveredAsset, ...]:
        del secrets
        self._validate(connection)
        return ()

    def read(
        self,
        connection: ConnectionDefinition,
        asset: AssetHandle,
        secrets: SecretResolver,
        *,
        limit: int = 10_000,
        checkpoint: SourceCheckpoint | None = None,
    ) -> ConnectorReadResult:
        if checkpoint is not None and checkpoint.strategy != "snapshot":
            raise ValueError("HTTP JSON connector only supports snapshot checkpoints")
        if limit < 1 or limit > 100_000:
            raise ValueError("HTTP read limit must be between 1 and 100000")
        if asset.connection_id != connection.id:
            raise ValueError("HTTP asset handle belongs to a different connection")
        base_url, options = self._validate(connection)
        parsed_base_url = urlsplit(base_url)
        _validate_endpoint_host(
            parsed_base_url.hostname or "",
            allow_private=options.get("allow_private_network", "false").casefold() == "true",
        )
        components = (*asset.namespace, asset.name)
        if any(not part or part in {".", ".."} or "://" in part for part in components):
            raise ValueError("HTTP asset path contains an unsafe component")
        path = "/".join(quote(part, safe="-._~") for part in components)
        url = f"{base_url}/{path}"

        headers = {"Accept": "application/json"}
        refs = _secret_refs(connection)
        bearer = refs.get("bearer_token")
        if bearer is not None:
            material = secrets.resolve(bearer)
            headers["Authorization"] = f"Bearer {material.reveal_text()}"

        httpx = _httpx()
        timeout_seconds = float(options.get("timeout_seconds", "30"))
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise ValueError("HTTP timeout_seconds must be in (0, 300]")
        try:
            max_response_bytes = int(options.get("max_response_bytes", "10485760"))
        except ValueError as exc:
            raise ValueError("HTTP max_response_bytes must be an integer") from exc
        if max_response_bytes < 1 or max_response_bytes > 100 * 1024 * 1024:
            raise ValueError("HTTP max_response_bytes must be between 1 and 104857600")
        records_key = options.get("records_key")
        try:
            retries = int(options.get("max_retries", "0"))
            max_pages = int(options.get("max_pages", "1"))
            page_size = int(options.get("page_size", str(limit)))
            backoff = float(options.get("retry_backoff_seconds", "0.25"))
            rate_limit = float(options.get("rate_limit_seconds", "0"))
        except ValueError as exc:
            raise ValueError(
                "HTTP retry, pagination and rate-limit options must be numeric"
            ) from exc
        if retries < 0 or retries > 10 or max_pages < 1 or max_pages > 1000:
            raise ValueError("HTTP max_retries must be 0..10 and max_pages must be 1..1000")
        if page_size < 1 or page_size > limit or backoff < 0 or rate_limit < 0:
            raise ValueError("HTTP page_size/backoff/rate-limit options are out of bounds")
        page_param = options.get("page_param")
        next_field = options.get("next_url_field")
        rows_list: list[dict[str, object]] = []
        bodies: list[bytes] = []
        next_url = url
        with httpx.Client(follow_redirects=False, timeout=timeout_seconds) as client:
            for page in range(max_pages):
                if page and rate_limit:
                    time.sleep(rate_limit)
                request_url = next_url
                if page_param and next_field is None:
                    separator = "&" if "?" in request_url else "?"
                    request_url = f"{request_url}{separator}{quote(page_param)}={page + 1}"
                body = b""
                for attempt in range(retries + 1):
                    try:
                        with client.stream("GET", request_url, headers=headers) as response:
                            status = response.status_code
                            if (status == 429 or 500 <= status <= 599) and attempt < retries:
                                retry_after = response.headers.get("retry-after")
                                delay = (
                                    float(retry_after) if retry_after else backoff * (2**attempt)
                                )
                                if delay > 0:
                                    time.sleep(min(delay, 60.0))
                                continue
                            response.raise_for_status()
                            content_type = (
                                response.headers.get("content-type", "")
                                .split(";", 1)[0]
                                .strip()
                                .lower()
                            )
                            if content_type not in {"application/json", "application/problem+json"}:
                                raise ValueError(
                                    "HTTP response content-type must be application/json"
                                )
                            content_length = response.headers.get("content-length")
                            if (
                                content_length is not None
                                and int(content_length) > max_response_bytes
                            ):
                                raise ValueError("HTTP JSON response exceeds configured byte limit")
                            chunks: list[bytes] = []
                            size = 0
                            for chunk in response.iter_bytes():
                                size += len(chunk)
                                if size > max_response_bytes:
                                    raise ValueError(
                                        "HTTP JSON response exceeds configured byte limit"
                                    )
                                chunks.append(chunk)
                            body = b"".join(chunks)
                        break
                    except (httpx.TimeoutException, httpx.NetworkError):
                        if attempt >= retries:
                            raise
                        time.sleep(min(backoff * (2**attempt), 60.0))
                try:
                    payload = json.loads(body)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError("HTTP response body must be valid JSON") from exc
                bodies.append(body)
                if records_key is not None:
                    if not isinstance(payload, Mapping):
                        raise ValueError("HTTP records_key requires a JSON object response")
                    page_records = payload.get(records_key)
                else:
                    page_records = payload
                if not isinstance(page_records, list) or not all(
                    isinstance(item, Mapping) for item in page_records
                ):
                    raise ValueError("HTTP JSON response must resolve to an array of records")
                rows_list.extend(dict(item) for item in page_records)
                if len(rows_list) > limit:
                    raise ValueError("HTTP JSON response exceeds requested row limit")
                if next_field is None:
                    if not page_param or len(page_records) < page_size:
                        break
                else:
                    if not isinstance(payload, Mapping):
                        raise ValueError("HTTP next_url_field requires a JSON object response")
                    candidate = payload.get(next_field)
                    if not candidate:
                        break
                    if not isinstance(candidate, str) or not candidate.startswith(
                        ("https://", "http://")
                    ):
                        raise ValueError("HTTP next_url_field must contain an absolute URL")
                    next_url = candidate
        rows = tuple(rows_list)
        fields = _infer_fields(rows)
        checkpoint_value = hashlib.sha256(b"".join(bodies)).hexdigest()
        if checkpoint is not None and checkpoint.value == checkpoint_value:
            rows = ()
        return ConnectorReadResult(
            fields,
            rows,
            SourceCheckpoint("snapshot", checkpoint_value),
        )


__all__ = ("HttpConnectorDependencyError", "HttpJsonConnector")
