"""Executable connector adapters for Ronin Public v1."""

from .azure_blob_json import AzureBlobJsonConnector
from .checkpoint import (
    CheckpointEvidence,
    CheckpointFenceConflict,
    CheckpointHealth,
    SqliteConnectorCheckpointStore,
)
from .contracts import Connector, ConnectorReadResult, DiscoveryPage, PagedConnector
from .http import IngestionHTTPAdapter
from .http_json import HttpJsonConnector
from .jdbc import (
    JdbcBridgeProvenance,
    JdbcConnector,
    JdbcDependencyError,
    JdbcIncrementalCheckpointV2,
)
from .ozone import OzoneJsonConnector
from .postgres import PostgresConnector
from .registry import ConnectorCapabilityRecord, ConnectorRegistry, builtin_connector_registry
from .s3_json import S3JsonConnector
from .sync import (
    ArtifactDestinationWriter,
    IngestionSyncDefinition,
    IngestionSyncPlan,
    IngestionSyncService,
    plan_sync,
)

__all__ = (
    "Connector",
    "ConnectorReadResult",
    "DiscoveryPage",
    "PagedConnector",
    "AzureBlobJsonConnector",
    "ConnectorRegistry",
    "ConnectorCapabilityRecord",
    "CheckpointEvidence",
    "CheckpointFenceConflict",
    "CheckpointHealth",
    "JdbcBridgeProvenance",
    "SqliteConnectorCheckpointStore",
    "builtin_connector_registry",
    "HttpJsonConnector",
    "IngestionHTTPAdapter",
    "JdbcConnector",
    "JdbcDependencyError",
    "JdbcIncrementalCheckpointV2",
    "PostgresConnector",
    "S3JsonConnector",
    "OzoneJsonConnector",
    "IngestionSyncDefinition",
    "ArtifactDestinationWriter",
    "IngestionSyncPlan",
    "IngestionSyncService",
    "plan_sync",
)
