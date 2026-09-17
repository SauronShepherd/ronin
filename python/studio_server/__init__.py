"""HTTP control-plane adapters over shared Ronin application services."""

from __future__ import annotations

from studio_execution import DurableExecutionService, WorkerPollResult

from studio_server.composition import LocalServerComposition
from studio_server.control_plane import (
    CONTROL_PLANE_ROUTES,
    ControlPlaneAuthenticator,
    ControlPlaneAuthorizer,
    ControlPlaneUnavailable,
    WorkspaceProjectHTTPServer,
)
from studio_server.http import SUPPORTED_ROUTES, DurableHTTPApplication
from studio_server.oidc_admin import OidcAdminRoninHTTPServer
from studio_server.oidc_http import OidcRoninHTTPServer
from studio_server.scoped_http import RoninHTTPServer
from studio_server.static_control_plane import (
    StaticControlPlaneAuthenticator,
    StaticControlPlaneAuthorizer,
)

__all__ = (
    "CONTROL_PLANE_ROUTES",
    "ControlPlaneAuthenticator",
    "ControlPlaneAuthorizer",
    "ControlPlaneUnavailable",
    "DurableExecutionService",
    "DurableHTTPApplication",
    "LocalServerComposition",
    "OidcAdminRoninHTTPServer",
    "OidcRoninHTTPServer",
    "RoninHTTPServer",
    "StaticControlPlaneAuthenticator",
    "StaticControlPlaneAuthorizer",
    "SUPPORTED_ROUTES",
    "WorkerPollResult",
    "WorkspaceProjectHTTPServer",
)
