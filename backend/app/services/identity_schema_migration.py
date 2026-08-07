"""Small idempotent schema bridge for existing local SQLite installations.

Fresh databases are fully described by ``Base.metadata``. SQLAlchemy's
``create_all`` intentionally does not add columns to an existing table, so this
bridge adds the two nullable agent ownership columns introduced with enterprise
identity. A versioned migration framework should replace this helper before
future destructive or data-transforming schema changes are introduced.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, inspect
from sqlalchemy.exc import OperationalError

from app.db import Base
from app.models import Agent


IDENTITY_TABLES = (
    "organizations",
    "app_users",
    "auth_identities",
    "organization_memberships",
    "app_sessions",
    "oidc_login_transactions",
    "security_audit_events",
)

AGENT_IDENTITY_COLUMNS = (
    "organization_id",
    "created_by_user_id",
)


@dataclass(frozen=True)
class IdentitySchemaMigrationResult:
    created_tables: tuple[str, ...]
    added_agent_columns: tuple[str, ...]
    added_identity_columns: tuple[str, ...]


def migrate_local_identity_schema(engine: Engine) -> IdentitySchemaMigrationResult:
    """Create identity tables and safely extend an existing SQLite ``agents``.

    The added columns are nullable, preserving every legacy and prebuilt agent.
    SQLite cannot add foreign-key constraints with ``ALTER TABLE ADD COLUMN``;
    fresh databases receive the declared constraints, while upgraded databases
    rely on application authorization and retain their data without a table
    rebuild. No current API deletes organizations or users.
    """

    if engine.dialect.name != "sqlite":
        raise RuntimeError(
            "migrate_local_identity_schema is only for SQLite; use a versioned "
            "database migration for other providers"
        )

    with engine.begin() as connection:
        before_tables = set(inspect(connection).get_table_names())
        Base.metadata.create_all(bind=connection)

        added_columns: list[str] = []
        added_identity_columns: list[str] = []
        current_columns = {
            column["name"] for column in inspect(connection).get_columns("agents")
        }
        for column_name in AGENT_IDENTITY_COLUMNS:
            if column_name in current_columns:
                continue
            model_column = Agent.__table__.c[column_name]
            compiled_type = model_column.type.compile(dialect=connection.dialect)
            try:
                connection.exec_driver_sql(
                    f'ALTER TABLE "agents" ADD COLUMN "{column_name}" {compiled_type}'
                )
            except OperationalError:
                # Web and worker processes may start together. Treat a concurrent
                # successful addition as idempotent, but never hide other errors.
                refreshed_columns = {
                    column["name"]
                    for column in inspect(connection).get_columns("agents")
                }
                if column_name not in refreshed_columns:
                    raise
            else:
                added_columns.append(column_name)
            current_columns.add(column_name)

        for index in Agent.__table__.indexes:
            indexed_columns = {column.name for column in index.columns}
            if indexed_columns.intersection(AGENT_IDENTITY_COLUMNS):
                index.create(bind=connection, checkfirst=True)

        # Invalidate any pre-browser-binding login flows created by an earlier
        # development build. A nullable SQLite bridge is intentional: new ORM
        # writes always provide the hash, while a legacy NULL can never pass the
        # callback check. Fresh schemas retain the model's NOT NULL constraint.
        transaction_columns = {
            column["name"]
            for column in inspect(connection).get_columns("oidc_login_transactions")
        }
        if "browser_binding_hash" not in transaction_columns:
            try:
                connection.exec_driver_sql(
                    'ALTER TABLE "oidc_login_transactions" '
                    'ADD COLUMN "browser_binding_hash" VARCHAR(64)'
                )
            except OperationalError:
                refreshed_columns = {
                    column["name"]
                    for column in inspect(connection).get_columns(
                        "oidc_login_transactions"
                    )
                }
                if "browser_binding_hash" not in refreshed_columns:
                    raise
            else:
                added_identity_columns.append(
                    "oidc_login_transactions.browser_binding_hash"
                )
            connection.exec_driver_sql('DELETE FROM "oidc_login_transactions"')

        after_tables = set(inspect(connection).get_table_names())

    created_tables = tuple(
        table_name
        for table_name in IDENTITY_TABLES
        if table_name not in before_tables and table_name in after_tables
    )
    return IdentitySchemaMigrationResult(
        created_tables=created_tables,
        added_agent_columns=tuple(added_columns),
        added_identity_columns=tuple(added_identity_columns),
    )
