"""Executable connector adapters for Ronin Public v1."""

from .azure_blob_json import AzureBlobJsonConnector
from .contracts import Connector, ConnectorReadResult
from .http_json import HttpJsonConnector
from .jdbc import JdbcConnector, JdbcDependencyError
from .postgres import PostgresConnector
from .registry import ConnectorRegistry, builtin_connector_registry
from .s3_json import S3JsonConnector
from .ozone import OzoneJsonConnector

__all__ = (
    "Connector",
    "ConnectorReadResult",
    "AzureBlobJsonConnector",
    "ConnectorRegistry",
    "builtin_connector_registry",
    "HttpJsonConnector",
    "JdbcConnector",
    "JdbcDependencyError",
    "PostgresConnector",
    "S3JsonConnector",
    "OzoneJsonConnector",
)
