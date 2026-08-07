"""SQLAlchemy-backed persistence service for local/open-source deployments."""

import logging
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, or_

from app import config
from app.db import SessionLocal
from app.models import (
    Agent,
    AgentQuestion,
    AppUser,
    Organization,
    OrganizationMembership,
    ReportChange,
    SavedReport,
    SavedReportDocument,
)
from app.services.diff_service import DiffService
from app.services.filesystem_storage_service import get_filesystem_storage_service
from app.services.template_security import (
    TemplateSecurityError,
    sanitize_custom_agent_template,
    sanitize_custom_template_css,
    sanitize_custom_template_html,
)

logger = logging.getLogger(__name__)


def _to_uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("Invalid datetime value %r; falling back to now", value)
    return datetime.now(timezone.utc)


class SqlAlchemyPersistenceService:
    """Persistence service with the same core surface as SupabaseService."""

    supports_organization_agents = True

    def __init__(self):
        self.diff_service = DiffService()
        logger.info("SQLAlchemy persistence service initialized")

    @contextmanager
    def _session(self):
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _storage_service(self):
        if config.STORAGE_PROVIDER == "filesystem":
            return get_filesystem_storage_service()
        return None

    def _agent_to_dict(self, agent: Agent) -> Dict[str, Any]:
        report_template = agent.report_template
        report_template_css = agent.report_template_css
        if agent.is_custom:
            try:
                report_template, report_template_css = sanitize_custom_agent_template(
                    report_template,
                    report_template_css,
                )
            except TemplateSecurityError:
                logger.warning(
                    "Disabled an unsafe legacy custom-agent template during read",
                    extra={"agent_id": str(agent.id)},
                )
                report_template = (
                    "<p>This report template was disabled because it contains "
                    "unsupported active content.</p>"
                )
                report_template_css = None

        return {
            "id": str(agent.id),
            "name": agent.name,
            "description": agent.description,
            "report_template": report_template,
            "report_template_css": report_template_css,
            "user_id": agent.user_id,
            "organization_id": (
                str(agent.organization_id)
                if getattr(agent, "organization_id", None) is not None
                else None
            ),
            "created_by_user_id": (
                str(agent.created_by_user_id)
                if getattr(agent, "created_by_user_id", None) is not None
                else None
            ),
            "is_custom": agent.is_custom,
            "created_by_name": agent.created_by_name,
            "created_at": agent.created_at,
            "updated_at": agent.updated_at,
            "agent_questions": [
                {
                    "id": str(question.id),
                    "agent_id": str(question.agent_id),
                    "placeholder": question.placeholder,
                    "prompt": question.prompt,
                }
                for question in agent.questions
            ],
        }

    def _report_to_dict(self, report: SavedReport) -> Dict[str, Any]:
        report_data = deepcopy(report.report_data)
        # Custom agents use UUID identifiers; bundled prebuilt agents use
        # trusted string slugs. Re-sanitize UUID-backed snapshots on every read
        # so reports saved before this security boundary cannot retain active
        # template markup or resource-loading CSS.
        if _to_uuid(report.agent_id) is not None and isinstance(report_data, dict):
            template = report_data.get("template")
            if isinstance(template, dict) and isinstance(template.get("html"), str):
                try:
                    safe_html, safe_css = sanitize_custom_agent_template(
                        template["html"],
                        template.get("css"),
                    )
                except TemplateSecurityError:
                    safe_html = (
                        "<p>This saved report template was disabled because it "
                        "contains unsupported active content.</p>"
                    )
                    safe_css = None
                template["html"] = safe_html
                template["css"] = safe_css

        return {
            "id": str(report.id),
            "user_id": report.user_id,
            "agent_id": report.agent_id,
            "agent_name": report.agent_name,
            "report_name": report.report_name,
            "report_data": report_data,
            "ai_baseline_answers": report.ai_baseline_answers,
            "generated_at": report.generated_at,
            "saved_at": report.saved_at,
        }

    def _document_to_dict(self, document: SavedReportDocument) -> Dict[str, Any]:
        return {
            "id": str(document.id),
            "report_id": str(document.report_id),
            "document_id": document.document_id,
            "filename": document.filename,
            "metadata": document.document_metadata or {},
            "storage_path": document.storage_path,
            "content_hash": document.content_hash,
            "storage_bucket": document.storage_bucket,
            "stored_at": _to_iso(document.stored_at),
            "created_at": _to_iso(document.created_at),
        }

    def _get_report(self, session, user_id: str, report_id: str) -> SavedReport | None:
        report_uuid = _to_uuid(report_id)
        if not report_uuid:
            return None
        return (
            session.query(SavedReport)
            .filter(SavedReport.id == report_uuid, SavedReport.user_id == str(user_id))
            .first()
        )

    def save_report(
        self,
        user_jwt: str,
        user_id: str,
        agent_id: str,
        agent_name: str,
        report_name: str,
        report_data: dict,
        document_contents: dict,
        pdf_binaries: Optional[Dict[str, bytes]] = None,
        refresh_token: str = "",
        existing_report_id: Optional[str] = None,
        cached_ai_baseline: Optional[Dict[str, str]] = None,
    ) -> str:
        return self._save_report_internal(
            user_id=user_id,
            agent_id=agent_id,
            agent_name=agent_name,
            report_name=report_name,
            report_data=report_data,
            document_contents=document_contents,
            pdf_binaries=pdf_binaries,
            access_token=user_jwt,
            refresh_token=refresh_token,
            existing_report_id=existing_report_id,
            cached_ai_baseline=cached_ai_baseline,
        )

    def save_report_for_system(
        self,
        user_id: str,
        agent_id: str,
        agent_name: str,
        report_name: str,
        report_data: dict,
        document_contents: dict,
        pdf_binaries: Optional[Dict[str, bytes]] = None,
        cached_ai_baseline: Optional[Dict[str, str]] = None,
    ) -> str:
        return self._save_report_internal(
            user_id=user_id,
            agent_id=agent_id,
            agent_name=agent_name,
            report_name=report_name,
            report_data=report_data,
            document_contents=document_contents,
            pdf_binaries=pdf_binaries,
            access_token="",
            refresh_token="",
            existing_report_id=None,
            cached_ai_baseline=cached_ai_baseline,
        )

    def _save_report_internal(
        self,
        user_id: str,
        agent_id: str,
        agent_name: str,
        report_name: str,
        report_data: dict,
        document_contents: dict,
        pdf_binaries: Optional[Dict[str, bytes]] = None,
        access_token: str = "",
        refresh_token: str = "",
        existing_report_id: Optional[str] = None,
        cached_ai_baseline: Optional[Dict[str, str]] = None,
    ) -> str:
        report_uuid = _to_uuid(existing_report_id) if existing_report_id else uuid4()
        generated_at = _parse_datetime(report_data.get("generated_at"))

        with self._session() as session:
            if existing_report_id:
                report = self._get_report(session, user_id, existing_report_id)
                if not report:
                    raise ValueError("Saved report not found")
                report.agent_id = agent_id
                report.agent_name = agent_name
                report.report_name = report_name
                report.report_data = report_data
                report.generated_at = generated_at
                session.query(SavedReportDocument).filter(
                    SavedReportDocument.report_id == report.id
                ).delete()
            else:
                report = SavedReport(
                    id=report_uuid,
                    user_id=str(user_id),
                    agent_id=agent_id,
                    agent_name=agent_name,
                    report_name=report_name,
                    report_data=report_data,
                    generated_at=generated_at,
                    saved_at=datetime.now(timezone.utc),
                    ai_baseline_answers=cached_ai_baseline,
                )
                session.add(report)

            baseline = report.ai_baseline_answers or cached_ai_baseline
            storage_service = self._storage_service()
            pdf_binaries = pdf_binaries or {}

            for document_id, document_content in document_contents.items():
                metadata = document_content.get("metadata", {})
                storage_metadata: Dict[str, Any] = {}

                if storage_service and document_id in pdf_binaries:
                    storage_metadata = storage_service.upload_document(
                        access_token=access_token,
                        refresh_token=refresh_token,
                        user_id=str(user_id),
                        document_id=document_id,
                        pdf_bytes=pdf_binaries[document_id],
                        report_id=str(report.id),
                    )

                session.add(
                    SavedReportDocument(
                        report_id=report.id,
                        document_id=document_id,
                        filename=document_content["filename"],
                        document_metadata=metadata,
                        storage_path=storage_metadata.get("storage_path"),
                        content_hash=storage_metadata.get("content_hash"),
                        storage_bucket=storage_metadata.get("bucket"),
                        stored_at=_parse_datetime(storage_metadata.get("stored_at"))
                        if storage_metadata
                        else None,
                    )
                )

            if baseline:
                self._replace_report_changes(session, str(user_id), report, baseline, report_data)

            session.flush()
            return str(report.id)

    def get_user_reports(
        self,
        user_jwt: str,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        with self._session() as session:
            reports = (
                session.query(SavedReport)
                .filter(SavedReport.user_id == str(user_id))
                .order_by(SavedReport.saved_at.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            return [self._report_to_dict(report) for report in reports]

    def get_saved_report(self, user_jwt: str, user_id: str, report_id: str) -> Optional[Dict[str, Any]]:
        with self._session() as session:
            report = self._get_report(session, user_id, report_id)
            return self._report_to_dict(report) if report else None

    def get_saved_document_content(
        self,
        user_jwt: str,
        user_id: str,
        report_id: str,
        document_id: str,
    ) -> Optional[Dict[str, Any]]:
        document = self.get_saved_document_metadata(user_jwt, user_id, report_id, document_id)
        if not document:
            return None
        return {
            "document_id": document["document_id"],
            "filename": document["filename"],
            "metadata": document["metadata"],
        }

    def get_saved_report_documents(
        self,
        user_jwt: str,
        user_id: str,
        report_id: str,
    ) -> List[Dict[str, Any]]:
        with self._session() as session:
            report = self._get_report(session, user_id, report_id)
            if not report:
                return []
            return [self._document_to_dict(document) for document in report.documents]

    def get_saved_document_metadata(
        self,
        user_jwt: str,
        user_id: str,
        report_id: str,
        document_id: str,
    ) -> Optional[Dict[str, Any]]:
        with self._session() as session:
            report = self._get_report(session, user_id, report_id)
            if not report:
                return None
            document = (
                session.query(SavedReportDocument)
                .filter(
                    SavedReportDocument.report_id == report.id,
                    SavedReportDocument.document_id == document_id,
                )
                .first()
            )
            return self._document_to_dict(document) if document else None

    def download_saved_document_pdf(
        self,
        user_jwt: str,
        user_id: str,
        report_id: str,
        document_id: str,
        refresh_token: str = "",
    ) -> Optional[bytes]:
        document = self.get_saved_document_metadata(user_jwt, user_id, report_id, document_id)
        if not document or not document.get("storage_path"):
            return None

        storage_service = self._storage_service()
        if not storage_service:
            return None
        return storage_service.download_document(
            access_token=user_jwt,
            refresh_token=refresh_token,
            user_id=str(user_id),
            storage_path=document["storage_path"],
        )

    def get_saved_document_signed_url(
        self,
        user_jwt: str,
        user_id: str,
        report_id: str,
        document_id: str,
        refresh_token: str = "",
        expiry_seconds: int = 3600,
    ) -> Optional[str]:
        return None

    def update_saved_report(
        self,
        user_jwt: str,
        user_id: str,
        report_id: str,
        report_data: Optional[Dict[str, Any]] = None,
        report_name: Optional[str] = None,
    ) -> bool:
        with self._session() as session:
            report = self._get_report(session, user_id, report_id)
            if not report:
                return False

            if report_name is not None:
                report.report_name = report_name
            if report_data is not None:
                report.report_data = report_data
                if report.ai_baseline_answers:
                    self._replace_report_changes(
                        session,
                        str(user_id),
                        report,
                        report.ai_baseline_answers,
                        report_data,
                    )
            return True

    def delete_saved_report(
        self,
        user_jwt: str,
        user_id: str,
        report_id: str,
        refresh_token: str = "",
    ) -> bool:
        with self._session() as session:
            report = self._get_report(session, user_id, report_id)
            if not report:
                return False

            storage_service = self._storage_service()
            if storage_service:
                try:
                    storage_service.cleanup_report_documents(
                        access_token=user_jwt,
                        refresh_token=refresh_token,
                        user_id=str(user_id),
                        report_id=str(report.id),
                    )
                except Exception as exc:
                    logger.error("Failed to clean up filesystem documents: %s", exc)

            session.delete(report)
            return True

    def _extract_baseline_answers(self, report_data: Dict[str, Any]) -> Dict[str, str]:
        baseline = {}
        answers = report_data.get("answers", {})
        for placeholder, answer_data in answers.items():
            baseline[placeholder] = answer_data.get("answer", "")
        return baseline

    def _replace_report_changes(
        self,
        session,
        user_id: str,
        report: SavedReport,
        baseline_answers: Dict[str, str],
        current_report_data: Dict[str, Any],
    ) -> None:
        session.query(ReportChange).filter(ReportChange.report_id == report.id).delete()

        current_answers = {
            placeholder: answer_data.get("answer", "")
            for placeholder, answer_data in current_report_data.get("answers", {}).items()
        }

        for placeholder, baseline_text in baseline_answers.items():
            current_text = current_answers.get(placeholder, baseline_text)
            if not self.diff_service.has_changes(baseline_text, current_text):
                continue

            changes = self.diff_service.compute_answer_diff(
                baseline_text,
                current_text,
                placeholder,
            )
            for change in changes:
                session.add(
                    ReportChange(
                        report_id=report.id,
                        answer_placeholder=change["answer_placeholder"],
                        change_type=change["change_type"],
                        text_content=change["text_content"],
                        start_offset=change["start_offset"],
                        end_offset=change["end_offset"],
                        user_id=user_id,
                        user_name=user_id,
                    )
                )

    def get_report_with_audit_changes(
        self,
        user_jwt: str,
        user_id: str,
        report_id: str,
    ) -> Optional[Dict[str, Any]]:
        with self._session() as session:
            report = self._get_report(session, user_id, report_id)
            if not report:
                return None

            report_data = deepcopy(report.report_data)
            if "answers" in report_data:
                for placeholder, answer_data in report_data["answers"].items():
                    answer_html = answer_data.get("answer", "")
                    answer_data["answer_plain"] = self.diff_service.html_to_plain_text(answer_html)

            changes_by_placeholder: Dict[str, List[Dict[str, Any]]] = {}
            changes = (
                session.query(ReportChange)
                .filter(ReportChange.report_id == report.id)
                .order_by(ReportChange.answer_placeholder, ReportChange.start_offset)
                .all()
            )
            for change in changes:
                changes_by_placeholder.setdefault(change.answer_placeholder, []).append(
                    {
                        "id": str(change.id),
                        "change_type": change.change_type,
                        "text_content": change.text_content,
                        "start_offset": change.start_offset,
                        "end_offset": change.end_offset,
                        "user_name": change.user_name or user_id,
                        "created_at": change.created_at,
                        "answer_placeholder": change.answer_placeholder,
                    }
                )

            return {
                "report_id": str(report.id),
                "report_name": report.report_name,
                "agent_name": report.agent_name,
                "report_data": report_data,
                "changes": changes_by_placeholder,
                "has_changes": bool(changes),
            }

    def create_custom_agent(
        self,
        user_jwt: str,
        user_id: str,
        created_by_name: str,
        name: str,
        description: str,
        report_template: str,
        report_template_css: Optional[str] = None,
        questions: Optional[List[Dict[str, str]]] = None,
        *,
        organization_id: Optional[str] = None,
        created_by_user_id: Optional[str] = None,
    ) -> str:
        questions = questions or []
        organization_uuid = _to_uuid(organization_id)
        creator_uuid = _to_uuid(created_by_user_id)
        if organization_id is not None and organization_uuid is None:
            raise ValueError("organization_id must be a UUID")
        if created_by_user_id is not None and creator_uuid is None:
            raise ValueError("created_by_user_id must be a UUID")

        report_template, report_template_css = sanitize_custom_agent_template(
            report_template,
            report_template_css,
        )

        with self._session() as session:
            agent = Agent(
                name=name,
                description=description,
                report_template=report_template,
                report_template_css=report_template_css,
                user_id=str(user_id),
                organization_id=organization_uuid,
                created_by_user_id=creator_uuid,
                is_custom=True,
                created_by_name=created_by_name,
            )
            agent.questions = [
                AgentQuestion(
                    placeholder=question["placeholder"],
                    prompt=question["prompt"],
                )
                for question in questions
            ]
            session.add(agent)
            session.flush()
            return str(agent.id)

    def get_user_custom_agents(
        self,
        user_jwt: str,
        user_id: str,
        *,
        organization_id: Optional[str] = None,
        app_user_id: Optional[str] = None,
        organization_role: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._session() as session:
            query = session.query(Agent).filter(Agent.is_custom.is_(True))
            if organization_id is not None:
                organization_uuid = _to_uuid(organization_id)
                if organization_uuid is None:
                    return []
                query = query.filter(
                    or_(
                        Agent.organization_id == organization_uuid,
                        and_(
                            Agent.organization_id.is_(None),
                            Agent.user_id == str(user_id),
                        ),
                    )
                )
            else:
                query = query.filter(Agent.user_id == str(user_id))

            agents = query.order_by(Agent.created_at.desc()).all()
            return [self._agent_to_dict(agent) for agent in agents]

    def get_agent_by_id(
        self,
        user_jwt: str,
        user_id: str,
        agent_id: str,
        *,
        organization_id: Optional[str] = None,
        app_user_id: Optional[str] = None,
        organization_role: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        agent_uuid = _to_uuid(agent_id)
        if not agent_uuid:
            return None

        with self._session() as session:
            query = session.query(Agent).filter(
                Agent.id == agent_uuid,
                Agent.is_custom.is_(True),
            )
            if organization_id is not None:
                organization_uuid = _to_uuid(organization_id)
                if organization_uuid is None:
                    return None
                query = query.filter(
                    or_(
                        Agent.organization_id == organization_uuid,
                        and_(
                            Agent.organization_id.is_(None),
                            Agent.user_id == str(user_id),
                        ),
                    )
                )
            else:
                query = query.filter(Agent.user_id == str(user_id))

            agent = query.first()
            return self._agent_to_dict(agent) if agent else None

    def get_agent_by_id_system(self, agent_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        agent_uuid = _to_uuid(agent_id)
        if not agent_uuid:
            return None

        with self._session() as session:
            visible_organization_ids = (
                session.query(OrganizationMembership.organization_id)
                .join(
                    AppUser,
                    AppUser.id == OrganizationMembership.app_user_id,
                )
                .join(
                    Organization,
                    Organization.id == OrganizationMembership.organization_id,
                )
                .filter(
                    AppUser.resource_owner_id == str(user_id),
                    AppUser.status == "active",
                    OrganizationMembership.status == "active",
                    Organization.status == "active",
                )
            )
            agent = (
                session.query(Agent)
                .filter(
                    Agent.id == agent_uuid,
                    Agent.is_custom.is_(True),
                    or_(
                        and_(
                            Agent.organization_id.is_(None),
                            Agent.user_id == str(user_id),
                        ),
                        Agent.organization_id.in_(visible_organization_ids),
                    ),
                )
                .first()
            )
            return self._agent_to_dict(agent) if agent else None

    def update_custom_agent(
        self,
        user_jwt: str,
        user_id: str,
        agent_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        report_template: Optional[str] = None,
        report_template_css: Optional[str] = None,
        questions: Optional[List[Dict[str, str]]] = None,
        *,
        organization_id: Optional[str] = None,
        app_user_id: Optional[str] = None,
        organization_role: Optional[str] = None,
    ) -> bool:
        agent_uuid = _to_uuid(agent_id)
        if not agent_uuid:
            return False

        with self._session() as session:
            query = session.query(Agent).filter(
                Agent.id == agent_uuid,
                Agent.is_custom.is_(True),
            )
            if organization_id is not None:
                organization_uuid = _to_uuid(organization_id)
                if organization_uuid is None:
                    return False

                organization_role_normalized = (organization_role or "").strip().lower()
                if organization_role_normalized == "admin":
                    organization_permission = Agent.organization_id == organization_uuid
                else:
                    creator_uuid = _to_uuid(app_user_id)
                    creator_conditions = [
                        and_(
                            Agent.created_by_user_id.is_(None),
                            Agent.user_id == str(user_id),
                        )
                    ]
                    if creator_uuid is not None:
                        creator_conditions.insert(0, Agent.created_by_user_id == creator_uuid)
                    organization_permission = and_(
                        Agent.organization_id == organization_uuid,
                        or_(*creator_conditions),
                    )

                query = query.filter(
                    or_(
                        organization_permission,
                        and_(
                            Agent.organization_id.is_(None),
                            Agent.user_id == str(user_id),
                        ),
                    )
                )
            else:
                query = query.filter(Agent.user_id == str(user_id))

            agent = query.first()
            if not agent:
                return False

            sanitized_report_template = (
                sanitize_custom_template_html(report_template)
                if report_template is not None
                else None
            )
            sanitized_report_template_css = (
                sanitize_custom_template_css(report_template_css)
                if report_template_css is not None
                else None
            )

            if name is not None:
                agent.name = name
            if description is not None:
                agent.description = description
            if sanitized_report_template is not None:
                agent.report_template = sanitized_report_template
            if sanitized_report_template_css is not None:
                agent.report_template_css = sanitized_report_template_css
            agent.updated_at = datetime.now(timezone.utc)

            if questions is not None:
                agent.questions = [
                    AgentQuestion(
                        placeholder=question["placeholder"],
                        prompt=question["prompt"],
                    )
                    for question in questions
                ]

            return True

    def delete_custom_agent(
        self,
        user_jwt: str,
        user_id: str,
        agent_id: str,
        *,
        organization_id: Optional[str] = None,
        app_user_id: Optional[str] = None,
        organization_role: Optional[str] = None,
    ) -> bool:
        agent_uuid = _to_uuid(agent_id)
        if not agent_uuid:
            return False

        with self._session() as session:
            query = session.query(Agent).filter(
                Agent.id == agent_uuid,
                Agent.is_custom.is_(True),
            )
            if organization_id is not None:
                organization_uuid = _to_uuid(organization_id)
                if organization_uuid is None:
                    return False

                organization_role_normalized = (organization_role or "").strip().lower()
                if organization_role_normalized == "admin":
                    organization_permission = Agent.organization_id == organization_uuid
                else:
                    creator_uuid = _to_uuid(app_user_id)
                    creator_conditions = [
                        and_(
                            Agent.created_by_user_id.is_(None),
                            Agent.user_id == str(user_id),
                        )
                    ]
                    if creator_uuid is not None:
                        creator_conditions.insert(0, Agent.created_by_user_id == creator_uuid)
                    organization_permission = and_(
                        Agent.organization_id == organization_uuid,
                        or_(*creator_conditions),
                    )

                query = query.filter(
                    or_(
                        organization_permission,
                        and_(
                            Agent.organization_id.is_(None),
                            Agent.user_id == str(user_id),
                        ),
                    )
                )
            else:
                query = query.filter(Agent.user_id == str(user_id))

            agent = query.first()
            if not agent:
                return False

            session.delete(agent)
            return True
