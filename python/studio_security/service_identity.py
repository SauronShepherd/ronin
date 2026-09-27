"""Explicit lifecycle operations for non-human service principals."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .contracts import Principal, PrincipalId


class ServiceIdentityError(ValueError):
    """Raised when a service identity lifecycle transition is invalid."""


class ServiceIdentityStore(Protocol):
    def get_principal(self, principal_id: PrincipalId) -> Principal | None: ...

    def put_principal(self, principal: Principal) -> Principal: ...


@dataclass(frozen=True)
class ServiceIdentityTransition:
    action: str
    principal_id: str
    replacement_id: str | None = None


class ServiceIdentityLifecycle:
    """Create, disable and explicitly rotate service principals."""

    def __init__(
        self,
        store: ServiceIdentityStore,
        *,
        on_transition: Callable[[ServiceIdentityTransition], None] | None = None,
    ) -> None:
        self._store = store
        self._on_transition = on_transition

    def _emit(self, transition: ServiceIdentityTransition) -> ServiceIdentityTransition:
        if self._on_transition is not None:
            self._on_transition(transition)
        return transition

    def create(
        self, principal_id: str, *, display_name: str, issuer: str, subject: str
    ) -> Principal:
        if not all(
            isinstance(value, str) and value and value.strip() == value
            for value in (principal_id, display_name, issuer, subject)
        ):
            raise ServiceIdentityError("service identity fields must be non-empty strings")
        principal = Principal(
            PrincipalId(principal_id), "service", display_name, issuer, subject, None, True
        )
        if self._store.get_principal(principal.id) is not None:
            raise ServiceIdentityError("service identity already exists")
        stored = self._store.put_principal(principal)
        self._emit(ServiceIdentityTransition("create", principal_id))
        return stored

    def disable(self, principal_id: str) -> ServiceIdentityTransition:
        current = self._store.get_principal(PrincipalId(principal_id))
        if current is None or current.kind != "service":
            raise ServiceIdentityError("service identity does not exist")
        if current.active:
            self._store.put_principal(
                Principal(
                    current.id,
                    "service",
                    current.display_name,
                    current.issuer,
                    current.subject,
                    current.email,
                    False,
                )
            )
        return self._emit(ServiceIdentityTransition("disable", principal_id))

    def rotate(
        self,
        principal_id: str,
        replacement_id: str,
        *,
        subject: str,
        display_name: str | None = None,
        issuer: str | None = None,
    ) -> Principal:
        current = self._store.get_principal(PrincipalId(principal_id))
        if current is None or current.kind != "service" or not current.active:
            raise ServiceIdentityError("active service identity does not exist")
        replacement = self.create(
            replacement_id,
            display_name=display_name or current.display_name,
            issuer=issuer or current.issuer,
            subject=subject,
        )
        self.disable(principal_id)
        self._emit(ServiceIdentityTransition("rotate", principal_id, replacement_id))
        return replacement


__all__ = ("ServiceIdentityError", "ServiceIdentityLifecycle", "ServiceIdentityTransition")
