"""Executable connector adapters for Ronin Public v1."""

from .azure_blob_json import AzureBlobJsonConnector
from .contracts import Connector, ConnectorReadResult, DiscoveryPage
from .http_json import HttpJsonConnector
from .jdbc import JdbcConnector, JdbcDependencyError, JdbcIncrementalCheckpointV2
from .ozone import OzoneJsonConnector
from .postgres import PostgresConnector
from .registry import ConnectorRegistry, builtin_connector_registry
from .s3_json import S3JsonConnector

__all__ = (
    "Connector",
    "ConnectorReadResult",
    "DiscoveryPage",
    "AzureBlobJsonConnector",
    "ConnectorRegistry",
    "builtin_connector_registry",
    "HttpJsonConnector",
    "JdbcConnector",
    "JdbcDependencyError",
    "JdbcIncrementalCheckpointV2",
    "PostgresConnector",
    "S3JsonConnector",
    "OzoneJsonConnector",
)
