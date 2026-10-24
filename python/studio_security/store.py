from __future__ import annotations

import sqlite3
from pathlib import Path

from .contracts import Principal, PrincipalId


class IdentityConflict(RuntimeError):
    """Raised when a service identity ID or issuer/subject pair is rebound."""


class SqliteServiceIdentityStore:
    """Persist service identities used by local workers; it cannot manage users or roles."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS security_service_identities (
                    identity_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    issuer TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    active INTEGER NOT NULL CHECK (active IN (0, 1)),
                    UNIQUE(issuer, subject)
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def put_service_identity(self, principal: Principal) -> Principal:
        if principal.kind != "service":
            raise ValueError("only service identities can be stored in Public v1")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            by_subject = connection.execute(
                "SELECT identity_id FROM security_service_identities WHERE issuer=? AND subject=?",
                (principal.issuer, principal.subject),
            ).fetchone()
            if by_subject is not None and str(by_subject[0]) != principal.id.value:
                raise IdentityConflict("service issuer/subject belongs to another identity")
            current = connection.execute(
                "SELECT display_name,issuer,subject FROM security_service_identities "
                "WHERE identity_id=?",
                (principal.id.value,),
            ).fetchone()
            if current is not None and (current[1], current[2]) != (
                principal.issuer,
                principal.subject,
            ):
                raise IdentityConflict("service identity ID cannot be rebound to another subject")
            connection.execute(
                """INSERT INTO security_service_identities
                   (identity_id,display_name,issuer,subject,active) VALUES (?,?,?,?,?)
                   ON CONFLICT(identity_id) DO UPDATE SET
                     display_name=excluded.display_name, active=excluded.active""",
                (
                    principal.id.value,
                    principal.display_name,
                    principal.issuer,
                    principal.subject,
                    int(principal.active),
                ),
            )
            connection.commit()
            return principal
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_service_identity(self, identity_id: PrincipalId) -> Principal | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT identity_id,display_name,issuer,subject,active
                   FROM security_service_identities WHERE identity_id=?""",
                (identity_id.value,),
            ).fetchone()
        if row is None:
            return None
        return Principal(
            PrincipalId(str(row[0])),
            "service",
            str(row[1]),
            str(row[2]),
            str(row[3]),
            None,
            bool(row[4]),
        )


__all__ = ("IdentityConflict", "SqliteServiceIdentityStore")
