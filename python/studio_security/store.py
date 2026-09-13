"""Durable SQLite identity/group/RBAC store for the Ronin reference profile."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from studio_core import WorkspaceId

from .contracts import Group, GroupId, Principal, PrincipalId, RoleBinding


class IdentityConflict(RuntimeError):
    """Raised when stable identity is reused with conflicting external subject data."""


class SqliteIdentityStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS security_principals (
                    principal_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    issuer TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    email TEXT,
                    active INTEGER NOT NULL,
                    UNIQUE(issuer, subject)
                );
                CREATE TABLE IF NOT EXISTS security_groups (
                    group_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS security_group_members (
                    group_id TEXT NOT NULL REFERENCES security_groups(group_id) ON DELETE CASCADE,
                    principal_id TEXT NOT NULL REFERENCES security_principals(principal_id) ON DELETE CASCADE,
                    PRIMARY KEY(group_id, principal_id)
                );
                CREATE TABLE IF NOT EXISTS security_role_bindings (
                    workspace_id TEXT NOT NULL,
                    subject_kind TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    PRIMARY KEY(workspace_id, subject_kind, subject_id, role)
                );
                CREATE INDEX IF NOT EXISTS security_role_subject_idx
                    ON security_role_bindings(subject_kind, subject_id, workspace_id);
                """
            )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _principal(row: tuple[object, ...]) -> Principal:
        return Principal(
            PrincipalId(str(row[0])),
            str(row[1]),  # type: ignore[arg-type]
            str(row[2]),
            str(row[3]),
            str(row[4]),
            None if row[5] is None else str(row[5]),
            bool(row[6]),
        )

    def put_principal(self, principal: Principal) -> Principal:
        payload = (
            principal.kind,
            principal.display_name,
            principal.issuer,
            principal.subject,
            principal.email,
            1 if principal.active else 0,
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            subject_row = connection.execute(
                "SELECT principal_id FROM security_principals WHERE issuer=? AND subject=?",
                (principal.issuer, principal.subject),
            ).fetchone()
            if subject_row is not None and subject_row[0] != principal.id.value:
                raise IdentityConflict(
                    "external issuer/subject is already bound to a different principal"
                )
            row = connection.execute(
                "SELECT kind,display_name,issuer,subject,email,active FROM security_principals "
                "WHERE principal_id=?",
                (principal.id.value,),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO security_principals("
                    "principal_id,kind,display_name,issuer,subject,email,active) VALUES (?,?,?,?,?,?,?)",
                    (principal.id.value, *payload),
                )
            elif tuple(row) != payload:
                if row[2] != principal.issuer or row[3] != principal.subject or row[0] != principal.kind:
                    raise IdentityConflict(
                        "principal id cannot be rebound to a different identity kind or subject"
                    )
                connection.execute(
                    "UPDATE security_principals SET display_name=?,email=?,active=? WHERE principal_id=?",
                    (principal.display_name, principal.email, 1 if principal.active else 0, principal.id.value),
                )
            connection.commit()
            return principal
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_principal(self, principal_id: PrincipalId) -> Principal | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT principal_id,kind,display_name,issuer,subject,email,active "
                "FROM security_principals WHERE principal_id=?",
                (principal_id.value,),
            ).fetchone()
            return None if row is None else self._principal(tuple(row))
        finally:
            connection.close()

    def find_principal(self, issuer: str, subject: str) -> Principal | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT principal_id,kind,display_name,issuer,subject,email,active "
                "FROM security_principals WHERE issuer=? AND subject=?",
                (issuer, subject),
            ).fetchone()
            return None if row is None else self._principal(tuple(row))
        finally:
            connection.close()

    def put_group(self, group: Group) -> Group:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO security_groups(group_id,name) VALUES (?,?) "
                "ON CONFLICT(group_id) DO UPDATE SET name=excluded.name",
                (group.id.value, group.name),
            )
            connection.commit()
            return group
        finally:
            connection.close()

    def add_group_member(self, group_id: GroupId, principal_id: PrincipalId) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT OR IGNORE INTO security_group_members(group_id,principal_id) VALUES (?,?)",
                (group_id.value, principal_id.value),
            )
            connection.commit()
        finally:
            connection.close()

    def remove_group_member(self, group_id: GroupId, principal_id: PrincipalId) -> bool:
        connection = self._connect()
        try:
            cursor = connection.execute(
                "DELETE FROM security_group_members WHERE group_id=? AND principal_id=?",
                (group_id.value, principal_id.value),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def groups_for_principal(self, principal_id: PrincipalId) -> tuple[GroupId, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT group_id FROM security_group_members WHERE principal_id=? ORDER BY group_id",
                (principal_id.value,),
            ).fetchall()
            return tuple(GroupId(str(row[0])) for row in rows)
        finally:
            connection.close()

    def put_role_binding(self, binding: RoleBinding) -> RoleBinding:
        connection = self._connect()
        try:
            if binding.subject_kind == "principal":
                row = connection.execute(
                    "SELECT 1 FROM security_principals WHERE principal_id=?",
                    (binding.subject_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT 1 FROM security_groups WHERE group_id=?",
                    (binding.subject_id,),
                ).fetchone()
            if row is None:
                raise KeyError(f"role binding subject does not exist: {binding.subject_id}")
            connection.execute(
                "INSERT OR IGNORE INTO security_role_bindings("
                "workspace_id,subject_kind,subject_id,role) VALUES (?,?,?,?)",
                (
                    binding.workspace_id.value,
                    binding.subject_kind,
                    binding.subject_id,
                    binding.role,
                ),
            )
            connection.commit()
            return binding
        finally:
            connection.close()

    def delete_role_binding(self, binding: RoleBinding) -> bool:
        connection = self._connect()
        try:
            cursor = connection.execute(
                "DELETE FROM security_role_bindings WHERE workspace_id=? AND subject_kind=? "
                "AND subject_id=? AND role=?",
                (
                    binding.workspace_id.value,
                    binding.subject_kind,
                    binding.subject_id,
                    binding.role,
                ),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def roles_for_actor(
        self,
        workspace_id: WorkspaceId,
        principal_id: PrincipalId,
    ) -> tuple[str, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT role
                FROM security_role_bindings
                WHERE workspace_id=? AND subject_kind='principal' AND subject_id=?
                UNION
                SELECT rb.role
                FROM security_role_bindings AS rb
                JOIN security_group_members AS gm
                  ON rb.subject_kind='group' AND rb.subject_id=gm.group_id
                WHERE rb.workspace_id=? AND gm.principal_id=?
                ORDER BY role
                """,
                (
                    workspace_id.value,
                    principal_id.value,
                    workspace_id.value,
                    principal_id.value,
                ),
            ).fetchall()
            return tuple(str(row[0]) for row in rows)
        finally:
            connection.close()


__all__ = ("IdentityConflict", "SqliteIdentityStore")
