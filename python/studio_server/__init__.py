"""HTTP control-plane adapters over shared Ronin application services."""

from __future__ import annotations

from studio_execution import DurableExecutionService, WorkerPollResult
from studio_quality import QualityHTTPAdapter
from studio_server.composition import LocalServerComposition
from studio_server.control_plane import (
    CONTROL_PLANE_ROUTES,
    CatalogReader,
    ControlPlaneAuthenticator,
    ControlPlaneAuthorizer,
    ControlPlaneUnavailable,
    PluginDiagnostics,
    PluginRouter,
    SemanticReader,
    StreamingHealthReader,
    WorkspaceProjectHTTPServer,
)
from studio_server.http import SUPPORTED_ROUTES, DurableHTTPApplication
from studio_server.oidc_admin import OIDC_ADMIN_ROUTES, OidcAdminRoninHTTPServer
from studio_server.oidc_http import OidcRoninHTTPServer
from studio_server.openlineage_http import HttpOpenLineageSink
from studio_server.scoped_http import RoninHTTPServer
from studio_server.static_control_plane import (
    StaticControlPlaneAuthenticator,
    StaticControlPlaneAuthorizer,
)

__all__ = (
    "CONTROL_PLANE_ROUTES",
    "CatalogReader",
    "StreamingHealthReader",
    "SemanticReader",
    "ControlPlaneAuthenticator",
    "ControlPlaneAuthorizer",
    "ControlPlaneUnavailable",
    "DurableExecutionService",
    "DurableHTTPApplication",
    "LocalServerComposition",
    "OidcAdminRoninHTTPServer",
    "OIDC_ADMIN_ROUTES",
    "OidcRoninHTTPServer",
    "RoninHTTPServer",
    "StaticControlPlaneAuthenticator",
    "StaticControlPlaneAuthorizer",
    "SUPPORTED_ROUTES",
    "WorkerPollResult",
    "WorkspaceProjectHTTPServer",
    "PluginDiagnostics",
    "PluginRouter",
    "QualityHTTPAdapter",
    "HttpOpenLineageSink",
)
