"""Apache Ozone S3 Gateway JSON/JSONL connector profile."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from studio_core import ConnectionDefinition, ConnectorDescriptor

from .s3_json import S3JsonConnector, _boto3


class OzoneJsonConnector(S3JsonConnector):
    """Use Apache Ozone's S3 Gateway with mandatory endpoint and path addressing."""

    descriptor = ConnectorDescriptor("ozone.s3.json", 1, S3JsonConnector.descriptor.capabilities)

    def _config(self, connection: ConnectionDefinition) -> tuple[str, str]:
        bucket, prefix = super()._config(connection)
        endpoint = dict(connection.options).get("endpoint_url", "").strip()
        if not endpoint:
            raise ValueError("Apache Ozone connector requires endpoint_url")
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Ozone endpoint_url must be an absolute HTTP(S) URL without query or fragment")
        return bucket, prefix

    def _client_for(self, connection: ConnectionDefinition) -> Any:
        if self._client is not None:
            return self._client
        options = dict(connection.options)
        try:
            config_module = __import__("botocore.config", fromlist=["Config"])
            config = config_module.Config(signature_version="s3v4", s3={"addressing_style": "path"})
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Apache Ozone connector requires boto3 and botocore") from exc
        kwargs: dict[str, object] = {"endpoint_url": options["endpoint_url"], "config": config}
        if options.get("region_name"):
            kwargs["region_name"] = options["region_name"]
        return _boto3().client("s3", **kwargs)


__all__ = ("OzoneJsonConnector",)
