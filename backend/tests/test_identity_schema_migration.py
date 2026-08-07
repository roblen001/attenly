import unittest

from sqlalchemy import Column, MetaData, String, Table, create_engine, inspect, select

from app.services.identity_schema_migration import (
    AGENT_IDENTITY_COLUMNS,
    IDENTITY_TABLES,
    migrate_local_identity_schema,
)


class IdentitySchemaMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")

    def tearDown(self):
        self.engine.dispose()

    def test_upgrades_legacy_agents_without_losing_rows_and_is_idempotent(self):
        legacy_metadata = MetaData()
        legacy_agents = Table(
            "agents",
            legacy_metadata,
            Column("id", String(36), primary_key=True),
            Column("name", String, nullable=False),
        )
        legacy_metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                legacy_agents.insert().values(id="legacy-agent", name="Legacy Agent")
            )

        first = migrate_local_identity_schema(self.engine)
        inspector = inspect(self.engine)
        agent_columns = {column["name"] for column in inspector.get_columns("agents")}
        table_names = set(inspector.get_table_names())

        self.assertEqual(
            set(first.added_agent_columns),
            set(AGENT_IDENTITY_COLUMNS),
        )
        self.assertTrue(set(IDENTITY_TABLES).issubset(table_names))
        self.assertTrue(set(AGENT_IDENTITY_COLUMNS).issubset(agent_columns))
        with self.engine.connect() as connection:
            rows = connection.execute(select(legacy_agents)).mappings().all()
        self.assertEqual(rows, [{"id": "legacy-agent", "name": "Legacy Agent"}])

        second = migrate_local_identity_schema(self.engine)
        self.assertEqual(second.created_tables, ())
        self.assertEqual(second.added_agent_columns, ())
        self.assertEqual(second.added_identity_columns, ())

    def test_fresh_schema_includes_agent_foreign_keys(self):
        result = migrate_local_identity_schema(self.engine)
        foreign_keys = inspect(self.engine).get_foreign_keys("agents")
        constrained_columns = {
            column
            for foreign_key in foreign_keys
            for column in foreign_key["constrained_columns"]
        }

        self.assertEqual(set(result.created_tables), set(IDENTITY_TABLES))
        self.assertIn("organization_id", constrained_columns)
        self.assertIn("created_by_user_id", constrained_columns)

    def test_invalidates_legacy_login_flows_when_adding_browser_binding(self):
        migrate_local_identity_schema(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                'ALTER TABLE "oidc_login_transactions" '
                'DROP COLUMN "browser_binding_hash"'
            )
            connection.exec_driver_sql(
                """
                INSERT INTO oidc_login_transactions (
                    id, organization_id, provider, state_hash, nonce,
                    code_verifier, redirect_uri, return_to, created_at,
                    expires_at, consumed_at
                ) VALUES (
                    '11111111111111111111111111111111',
                    '22222222222222222222222222222222',
                    'oidc', 'legacy-state-hash', 'legacy-nonce', 'verifier',
                    'https://attenly.example/api/auth/oidc/callback', '/',
                    '2026-08-03 12:00:00', '2026-08-03 12:10:00', NULL
                )
                """
            )

        result = migrate_local_identity_schema(self.engine)
        columns = {
            column["name"]
            for column in inspect(self.engine).get_columns("oidc_login_transactions")
        }
        with self.engine.connect() as connection:
            remaining = connection.exec_driver_sql(
                'SELECT COUNT(*) FROM "oidc_login_transactions"'
            ).scalar_one()

        self.assertIn("browser_binding_hash", columns)
        self.assertEqual(
            result.added_identity_columns,
            ("oidc_login_transactions.browser_binding_hash",),
        )
        self.assertEqual(remaining, 0)


if __name__ == "__main__":
    unittest.main()
