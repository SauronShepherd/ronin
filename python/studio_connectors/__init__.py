"""Executable connector adapters for Ronin Public v1."""

from .azure_blob_json import AzureBlobJsonConnector
from .checkpoint import (
    CheckpointEvidence,
    CheckpointFenceConflict,
    CheckpointHealth,
    PostgresConnectorCheckpointStore,
    SqliteConnectorCheckpointStore,
)
from .contracts import (
    Connector,
    ConnectorCapabilityError,
    ConnectorCommitResult,
    ConnectorReadResult,
    ConnectorWriter,
    DiscoveryPage,
    PagedConnector,
    TransactionalConnectorWriter,
)
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
    IngestionSyncCancelled,
    IngestionSyncDefinition,
    IngestionSyncPlan,
    IngestionSyncService,
    plan_sync,
    scoped_checkpoint_identity,
)

__all__ = (
    "Connector",
    "ConnectorCapabilityError",
    "ConnectorCommitResult",
    "ConnectorReadResult",
    "ConnectorWriter",
    "DiscoveryPage",
    "PagedConnector",
    "TransactionalConnectorWriter",
    "AzureBlobJsonConnector",
    "ConnectorRegistry",
    "ConnectorCapabilityRecord",
    "CheckpointEvidence",
    "CheckpointFenceConflict",
    "CheckpointHealth",
    "PostgresConnectorCheckpointStore",
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
    "IngestionSyncCancelled",
    "ArtifactDestinationWriter",
    "IngestionSyncPlan",
    "IngestionSyncService",
    "plan_sync",
    "scoped_checkpoint_identity",
)
