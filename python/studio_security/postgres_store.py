"""PostgreSQL identity/group/RBAC store for the shared Ronin server profile."""

from __future__ import annotations

from typing import Any, cast

from studio_core import WorkspaceId

from .contracts import (
    Group,
    GroupId,
    Principal,
    PrincipalId,
    PrincipalKind,
    RoleBinding,
)
from .store import IdentityConflict


class PostgresSecurityDependencyError(RuntimeError):
    """Raised when psycopg is unavailable for the PostgreSQL security profile."""


def _psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise PostgresSecurityDependencyError(
            "PostgreSQL identity/RBAC support requires psycopg from Ronin data-plane/server dependencies"
        ) from exc
    return psycopg, dict_row


_SCHEMA = """
CREATE TABLE IF NOT EXISTS ronin_security_principals (
    principal_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('user','service')),
    display_name TEXT NOT NULL,
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    email TEXT,
    active BOOLEAN NOT NULL,
    UNIQUE(issuer, subject)
);
CREATE TABLE IF NOT EXISTS ronin_security_groups (
    group_id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ronin_security_group_members (
    group_id TEXT NOT NULL REFERENCES ronin_security_groups(group_id) ON DELETE CASCADE,
    principal_id TEXT NOT NULL REFERENCES ronin_security_principals(principal_id) ON DELETE CASCADE,
    PRIMARY KEY(group_id, principal_id)
);
CREATE TABLE IF NOT EXISTS ronin_security_role_bindings (
    workspace_id TEXT NOT NULL,
    subject_kind TEXT NOT NULL CHECK (subject_kind IN ('principal','group')),
    subject_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin','operator','editor','viewer')),
    PRIMARY KEY(workspace_id, subject_kind, subject_id, role)
);
CREATE INDEX IF NOT EXISTS ronin_security_role_subject_idx
    ON ronin_security_role_bindings(subject_kind, subject_id, workspace_id);
CREATE INDEX IF NOT EXISTS ronin_security_member_principal_idx
    ON ronin_security_group_members(principal_id, group_id);
"""


def _unique_violation(exc: BaseException) -> bool:
    return getattr(exc, "sqlstate", None) == "23505"


class PostgresIdentityStore:
    """Shared PostgreSQL adapter implementing OIDC principal and RBAC store contracts."""

    def __init__(self, dsn: str, *, application_name: str = "ronin-security") -> None:
        if not dsn or dsn != dsn.strip():
            raise ValueError("PostgreSQL DSN must be non-empty and trimmed")
        if not application_name or application_name != application_name.strip():
            raise ValueError("application_name must be non-empty and trimmed")
        self._dsn = dsn
        self._application_name = application_name
        self.migrate()

    def _connect(self) -> Any:
        psycopg, dict_row = _psycopg()
        return psycopg.connect(
            self._dsn,
            autocommit=False,
            row_factory=dict_row,
            application_name=self._application_name,
        )

    def migrate(self) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(_SCHEMA)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _principal(row: dict[str, object]) -> Principal:
        return Principal(
            PrincipalId(str(row["principal_id"])),
            cast(PrincipalKind, str(row["kind"])),
            str(row["display_name"]),
            str(row["issuer"]),
            str(row["subject"]),
            None if row["email"] is None else str(row["email"]),
            bool(row["active"]),
        )

    def put_principal(self, principal: Principal) -> Principal:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT principal_id FROM ronin_security_principals "
                    "WHERE issuer=%s AND subject=%s FOR UPDATE",
                    (principal.issuer, principal.subject),
                )
                subject_row = cursor.fetchone()
                if subject_row is not None and subject_row["principal_id"] != principal.id.value:
                    raise IdentityConflict(
                        "external issuer/subject is already bound to a different principal"
                    )
                cursor.execute(
                    "SELECT * FROM ronin_security_principals WHERE principal_id=%s FOR UPDATE",
                    (principal.id.value,),
                )
                row = cursor.fetchone()
                if row is None:
                    cursor.execute(
                        "INSERT INTO ronin_security_principals("
                        "principal_id,kind,display_name,issuer,subject,email,active) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (
                            principal.id.value,
                            principal.kind,
                            principal.display_name,
                            principal.issuer,
                            principal.subject,
                            principal.email,
                            principal.active,
                        ),
                    )
                else:
                    existing = self._principal(row)
                    if (
                        existing.kind != principal.kind
                        or existing.issuer != principal.issuer
                        or existing.subject != principal.subject
                    ):
                        raise IdentityConflict(
                            "principal id cannot be rebound to a different identity kind or subject"
                        )
                    cursor.execute(
                        "UPDATE ronin_security_principals SET display_name=%s,email=%s,active=%s "
                        "WHERE principal_id=%s",
                        (
                            principal.display_name,
                            principal.email,
                            principal.active,
                            principal.id.value,
                        ),
                    )
            connection.commit()
            return principal
        except IdentityConflict:
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            if _unique_violation(exc):
                raise IdentityConflict("principal identity conflicts with durable state") from exc
            raise
        finally:
            connection.close()

    def get_principal(self, principal_id: PrincipalId) -> Principal | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM ronin_security_principals WHERE principal_id=%s",
                    (principal_id.value,),
                )
                row = cursor.fetchone()
            return None if row is None else self._principal(row)
        finally:
            connection.close()

    def find_principal(self, issuer: str, subject: str) -> Principal | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM ronin_security_principals WHERE issuer=%s AND subject=%s",
                    (issuer, subject),
                )
                row = cursor.fetchone()
            return None if row is None else self._principal(row)
        finally:
            connection.close()

    def put_group(self, group: Group) -> Group:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO ronin_security_groups(group_id,name) VALUES (%s,%s) "
                    "ON CONFLICT(group_id) DO UPDATE SET name=EXCLUDED.name",
                    (group.id.value, group.name),
                )
            connection.commit()
            return group
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def add_group_member(self, group_id: GroupId, principal_id: PrincipalId) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO ronin_security_group_members(group_id,principal_id) "
                    "VALUES (%s,%s) ON CONFLICT DO NOTHING",
                    (group_id.value, principal_id.value),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def remove_group_member(self, group_id: GroupId, principal_id: PrincipalId) -> bool:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM ronin_security_group_members WHERE group_id=%s AND principal_id=%s",
                    (group_id.value, principal_id.value),
                )
                removed = cursor.rowcount == 1
            connection.commit()
            return removed
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def groups_for_principal(self, principal_id: PrincipalId) -> tuple[GroupId, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT group_id FROM ronin_security_group_members "
                    "WHERE principal_id=%s ORDER BY group_id",
                    (principal_id.value,),
                )
                rows = cursor.fetchall()
            return tuple(GroupId(str(row["group_id"])) for row in rows)
        finally:
            connection.close()

    def put_role_binding(self, binding: RoleBinding) -> RoleBinding:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                if binding.subject_kind == "principal":
                    cursor.execute(
                        "SELECT 1 FROM ronin_security_principals WHERE principal_id=%s",
                        (binding.subject_id,),
                    )
                else:
                    cursor.execute(
                        "SELECT 1 FROM ronin_security_groups WHERE group_id=%s",
                        (binding.subject_id,),
                    )
                if cursor.fetchone() is None:
                    raise KeyError(f"role binding subject does not exist: {binding.subject_id}")
                cursor.execute(
                    "INSERT INTO ronin_security_role_bindings("
                    "workspace_id,subject_kind,subject_id,role) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT DO NOTHING",
                    (
                        binding.workspace_id.value,
                        binding.subject_kind,
                        binding.subject_id,
                        binding.role,
                    ),
                )
            connection.commit()
            return binding
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def delete_role_binding(self, binding: RoleBinding) -> bool:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM ronin_security_role_bindings WHERE workspace_id=%s "
                    "AND subject_kind=%s AND subject_id=%s AND role=%s",
                    (
                        binding.workspace_id.value,
                        binding.subject_kind,
                        binding.subject_id,
                        binding.role,
                    ),
                )
                removed = cursor.rowcount == 1
            connection.commit()
            return removed
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def roles_for_actor(
        self,
        workspace_id: WorkspaceId,
        principal_id: PrincipalId,
    ) -> tuple[str, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT DISTINCT rb.role FROM ronin_security_role_bindings rb "
                    "WHERE rb.workspace_id=%s AND ("
                    "(rb.subject_kind='principal' AND rb.subject_id=%s) OR "
                    "(rb.subject_kind='group' AND EXISTS ("
                    "SELECT 1 FROM ronin_security_group_members gm "
                    "WHERE gm.group_id=rb.subject_id AND gm.principal_id=%s))) "
                    "ORDER BY rb.role",
                    (workspace_id.value, principal_id.value, principal_id.value),
                )
                rows = cursor.fetchall()
            return tuple(str(row["role"]) for row in rows)
        finally:
            connection.close()


__all__ = ("PostgresIdentityStore", "PostgresSecurityDependencyError")
