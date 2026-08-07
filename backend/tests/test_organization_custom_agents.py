"""Authorization tests for organization-shared custom agents."""

import unittest
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import AppUser, Organization, OrganizationMembership
from app.services import sqlalchemy_persistence_service as persistence_module
from app.services.template_security import TemplateSecurityError


class OrganizationCustomAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_patch = mock.patch.object(
            persistence_module,
            "SessionLocal",
            self.session_factory,
        )
        self.session_patch.start()
        self.service = persistence_module.SqlAlchemyPersistenceService()

        with self.session_factory() as session:
            self.organization = Organization(slug="acme", name="Acme")
            self.other_organization = Organization(slug="other", name="Other")
            self.creator = AppUser(resource_owner_id="creator-owner")
            self.colleague = AppUser(resource_owner_id="colleague-owner")
            self.admin = AppUser(resource_owner_id="admin-owner")
            self.outsider = AppUser(resource_owner_id="outsider-owner")
            session.add_all(
                [
                    self.organization,
                    self.other_organization,
                    self.creator,
                    self.colleague,
                    self.admin,
                    self.outsider,
                ]
            )
            session.commit()

    def tearDown(self) -> None:
        self.session_patch.stop()
        self.engine.dispose()

    def _create_organization_agent(self, name: str = "Shared agent") -> str:
        return self.service.create_custom_agent(
            user_jwt="",
            user_id=self.creator.resource_owner_id,
            created_by_name="Creator",
            name=name,
            description="Shared in Acme",
            report_template="<p>Shared</p>",
            organization_id=str(self.organization.id),
            created_by_user_id=str(self.creator.id),
        )

    def _organization_context(self, user: AppUser, role: str = "user") -> dict:
        return {
            "organization_id": str(self.organization.id),
            "app_user_id": str(user.id),
            "organization_role": role,
        }

    def test_members_can_list_get_and_run_shared_agents_but_not_modify_them(self) -> None:
        agent_id = self._create_organization_agent()
        colleague_context = self._organization_context(self.colleague)

        listed = self.service.get_user_custom_agents(
            "",
            self.colleague.resource_owner_id,
            **colleague_context,
        )
        fetched = self.service.get_agent_by_id(
            "",
            self.colleague.resource_owner_id,
            agent_id,
            **colleague_context,
        )

        self.assertEqual([agent_id], [str(agent["id"]) for agent in listed])
        self.assertEqual(agent_id, str(fetched["id"]))
        self.assertEqual(str(self.organization.id), fetched["organization_id"])
        self.assertEqual(str(self.creator.id), fetched["created_by_user_id"])
        self.assertFalse(
            self.service.update_custom_agent(
                "",
                self.colleague.resource_owner_id,
                agent_id,
                name="Unauthorized edit",
                **colleague_context,
            )
        )
        self.assertFalse(
            self.service.delete_custom_agent(
                "",
                self.colleague.resource_owner_id,
                agent_id,
                **colleague_context,
            )
        )

    def test_creator_and_admin_can_modify_while_cross_org_admin_cannot(self) -> None:
        creator_agent_id = self._create_organization_agent("Creator-owned")
        admin_agent_id = self._create_organization_agent("Admin-managed")

        self.assertTrue(
            self.service.update_custom_agent(
                "",
                self.creator.resource_owner_id,
                creator_agent_id,
                name="Creator edit",
                **self._organization_context(self.creator),
            )
        )
        self.assertTrue(
            self.service.delete_custom_agent(
                "",
                self.admin.resource_owner_id,
                admin_agent_id,
                **self._organization_context(self.admin, role="admin"),
            )
        )
        self.assertFalse(
            self.service.update_custom_agent(
                "",
                self.outsider.resource_owner_id,
                creator_agent_id,
                name="Cross-org edit",
                organization_id=str(self.other_organization.id),
                app_user_id=str(self.outsider.id),
                organization_role="admin",
            )
        )

    def test_legacy_agents_remain_visible_only_to_their_resource_owner(self) -> None:
        legacy_agent_id = self.service.create_custom_agent(
            user_jwt="legacy-token",
            user_id=self.creator.resource_owner_id,
            created_by_name="Legacy creator",
            name="Legacy agent",
            description="Private legacy agent",
            report_template="<p>Legacy</p>",
        )

        owner_agents = self.service.get_user_custom_agents(
            "",
            self.creator.resource_owner_id,
            **self._organization_context(self.creator),
        )
        colleague_agents = self.service.get_user_custom_agents(
            "",
            self.colleague.resource_owner_id,
            **self._organization_context(self.colleague),
        )

        self.assertIn(legacy_agent_id, [str(agent["id"]) for agent in owner_agents])
        self.assertNotIn(legacy_agent_id, [str(agent["id"]) for agent in colleague_agents])
        self.assertTrue(
            self.service.update_custom_agent(
                "",
                self.creator.resource_owner_id,
                legacy_agent_id,
                name="Legacy owner edit",
                **self._organization_context(self.creator),
            )
        )
        self.assertIsNone(
            self.service.get_agent_by_id(
                "",
                self.colleague.resource_owner_id,
                legacy_agent_id,
                **self._organization_context(self.colleague),
            )
        )

    def test_background_runs_require_an_active_local_membership(self) -> None:
        agent_id = self._create_organization_agent()
        with self.session_factory() as session:
            membership = OrganizationMembership(
                organization_id=self.organization.id,
                app_user_id=self.colleague.id,
                role="user",
                status="active",
            )
            session.add(membership)
            session.commit()
            membership_id = membership.id

        self.assertIsNotNone(
            self.service.get_agent_by_id_system(
                agent_id,
                self.colleague.resource_owner_id,
            )
        )

        with self.session_factory() as session:
            membership = session.get(OrganizationMembership, membership_id)
            membership.status = "blocked"
            session.commit()

        self.assertIsNone(
            self.service.get_agent_by_id_system(
                agent_id,
                self.colleague.resource_owner_id,
            )
        )

    def test_create_and_update_persist_only_sanitized_templates(self) -> None:
        context = self._organization_context(self.creator)
        agent_id = self.service.create_custom_agent(
            user_jwt="",
            user_id=self.creator.resource_owner_id,
            created_by_name="Creator",
            name="Sanitized agent",
            description="Security test",
            report_template=(
                "<script>steal()</script>"
                "<p style='color:red' onclick='steal()'>{{answer}}</p>"
                "<img src='https://tracker.example/pixel' alt='Logo'>"
            ),
            report_template_css=(
                "@import url('https://tracker.example/theme.css');"
                ".report { color: red; background: url(file:///etc/passwd); }"
            ),
            organization_id=context["organization_id"],
            created_by_user_id=context["app_user_id"],
        )

        created = self.service.get_agent_by_id(
            "",
            self.creator.resource_owner_id,
            agent_id,
            **context,
        )
        self.assertIsNotNone(created)
        created_html = created["report_template"].casefold()
        created_css = (created["report_template_css"] or "").casefold()
        self.assertIn("{{answer}}", created_html)
        self.assertNotIn("script", created_html)
        self.assertNotIn("style=", created_html)
        self.assertNotIn("onclick", created_html)
        self.assertNotIn("src=", created_html)
        self.assertIn("color: red", created_css)
        self.assertNotIn("@import", created_css)
        self.assertNotIn("url", created_css)

        self.assertTrue(
            self.service.update_custom_agent(
                "",
                self.creator.resource_owner_id,
                agent_id,
                report_template="<section onmouseover='steal()'><p>Updated</p></section>",
                report_template_css=(
                    ".report { margin: 1rem; behavior: url(malware.htc); }"
                ),
                **context,
            )
        )
        updated = self.service.get_agent_by_id(
            "",
            self.creator.resource_owner_id,
            agent_id,
            **context,
        )
        self.assertNotIn("onmouseover", updated["report_template"].casefold())
        self.assertIn("Updated", updated["report_template"])
        self.assertIn("margin: 1rem", updated["report_template_css"])
        self.assertNotIn("behavior", updated["report_template_css"].casefold())
        self.assertNotIn("url", updated["report_template_css"].casefold())

    def test_create_rejects_template_without_safe_content(self) -> None:
        with self.assertRaises(TemplateSecurityError):
            self.service.create_custom_agent(
                user_jwt="",
                user_id=self.creator.resource_owner_id,
                created_by_name="Creator",
                name="Unsafe agent",
                description="Security test",
                report_template=(
                    "<script>steal()</script>"
                    "<iframe src='https://tracker.example/frame'></iframe>"
                ),
                organization_id=str(self.organization.id),
                created_by_user_id=str(self.creator.id),
            )


if __name__ == "__main__":
    unittest.main()
