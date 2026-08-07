import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import AppUser, Organization, OrganizationMembership
from app.services.filesystem_storage_service import FilesystemStorageService
from app.services import sqlalchemy_persistence_service as persistence_module


class OrganizationResourcePrivacyTests(unittest.TestCase):
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
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = FilesystemStorageService(self.temp_dir.name)

        with self.session_factory() as session:
            self.organization = Organization(slug="private-files", name="Private Files Corp")
            self.creator = AppUser(resource_owner_id="oidc-creator-private-owner")
            self.colleague = AppUser(resource_owner_id="oidc-colleague-private-owner")
            session.add_all([self.organization, self.creator, self.colleague])
            session.flush()
            session.add_all(
                [
                    OrganizationMembership(
                        organization_id=self.organization.id,
                        app_user_id=self.creator.id,
                        role="user",
                        status="active",
                    ),
                    OrganizationMembership(
                        organization_id=self.organization.id,
                        app_user_id=self.colleague.id,
                        role="user",
                        status="active",
                    ),
                ]
            )
            session.commit()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        self.session_patch.stop()
        self.engine.dispose()

    def test_shared_agent_does_not_broaden_report_or_document_ownership(self) -> None:
        organization_context = {
            "organization_id": str(self.organization.id),
            "app_user_id": str(self.colleague.id),
            "organization_role": "user",
        }
        shared_agent_id = self.service.create_custom_agent(
            user_jwt="",
            user_id=self.creator.resource_owner_id,
            created_by_name="Creator",
            name="Shared analysis",
            description="The agent is shared; its inputs and outputs are not.",
            report_template="<p>{{PrivateAnswer}}</p>",
            questions=[
                {
                    "placeholder": "PrivateAnswer",
                    "prompt": "Extract the private answer.",
                }
            ],
            organization_id=str(self.organization.id),
            created_by_user_id=str(self.creator.id),
        )
        self.assertIsNotNone(
            self.service.get_agent_by_id(
                "",
                self.colleague.resource_owner_id,
                shared_agent_id,
                **organization_context,
            )
        )

        private_pdf = b"%PDF-1.4\ncreator-private-document\n%%EOF"
        report_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "template": {
                "html": (
                    '<div class="report"><script>steal()</script>'
                    '<a href="https://attacker.example">Report</a>'
                    "<p>{{PrivateAnswer}}</p></div>"
                ),
                "css": (
                    ".template-isolated-content { position: fixed; inset: 0; } "
                    ".report { color: #123456; }"
                ),
                "questions": [],
            },
            "answers": {
                "{{PrivateAnswer}}": {
                    "id": "private-answer",
                    "answer": "creator confidential answer",
                    "quotes": [],
                }
            },
        }
        with mock.patch.object(self.service, "_storage_service", return_value=self.storage):
            report_id = self.service.save_report(
                user_jwt="",
                user_id=self.creator.resource_owner_id,
                agent_id=shared_agent_id,
                agent_name="Shared analysis",
                report_name="Creator private report",
                report_data=report_data,
                document_contents={
                    "private-document": {
                        "filename": "creator-confidential.pdf",
                        "metadata": {"classification": "confidential"},
                    }
                },
                pdf_binaries={"private-document": private_pdf},
            )

            owner_documents = self.service.get_saved_report_documents(
                "",
                self.creator.resource_owner_id,
                report_id,
            )
            self.assertEqual(len(owner_documents), 1)
            storage_path = owner_documents[0]["storage_path"]
            self.assertEqual(
                self.service.download_saved_document_pdf(
                    "",
                    self.creator.resource_owner_id,
                    report_id,
                    "private-document",
                ),
                private_pdf,
            )

            # Knowing the organization-shared agent ID, report UUID, document
            # ID, or filesystem path never broadens ownership to a colleague.
            self.assertEqual(
                self.service.get_user_reports("", self.colleague.resource_owner_id),
                [],
            )
            self.assertIsNone(
                self.service.get_saved_report(
                    "",
                    self.colleague.resource_owner_id,
                    report_id,
                )
            )
            self.assertEqual(
                self.service.get_saved_report_documents(
                    "",
                    self.colleague.resource_owner_id,
                    report_id,
                ),
                [],
            )
            self.assertIsNone(
                self.service.get_saved_document_metadata(
                    "",
                    self.colleague.resource_owner_id,
                    report_id,
                    "private-document",
                )
            )
            self.assertIsNone(
                self.service.download_saved_document_pdf(
                    "",
                    self.colleague.resource_owner_id,
                    report_id,
                    "private-document",
                )
            )
            self.assertFalse(
                self.service.update_saved_report(
                    "",
                    self.colleague.resource_owner_id,
                    report_id,
                    report_name="stolen",
                )
            )
            self.assertFalse(
                self.service.delete_saved_report(
                    "",
                    self.colleague.resource_owner_id,
                    report_id,
                )
            )
            with self.assertRaisesRegex(ValueError, "does not belong to user"):
                self.storage.download_document_for_system(
                    self.colleague.resource_owner_id,
                    storage_path,
                )

            owner_report = self.service.get_saved_report(
                "",
                self.creator.resource_owner_id,
                report_id,
            )
            self.assertIsNotNone(owner_report)
            safe_template = owner_report["report_data"]["template"]
            self.assertNotIn("<script", safe_template["html"].casefold())
            self.assertNotIn("href=", safe_template["html"].casefold())
            self.assertNotIn("template-isolated-content", safe_template["css"])
            self.assertNotIn("position", safe_template["css"])
            self.assertIn("color: #123456", safe_template["css"])


if __name__ == "__main__":
    unittest.main()
