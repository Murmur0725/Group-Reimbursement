import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import init_config, load_settings
from app.db.database import SessionLocal, init_db
from app.db.models import (
    NotionStatusUpdateAction,
    ReimbursementAttachment,
    ReimbursementRecord,
)
from app.notion_client import create_client, get_database_property_type, update_page_status
from app.schemas.reimbursement import AttachmentData, ReimbursementRecordData
from app.services.record_domain import (
    add_status_event,
    add_version,
    build_content_hash,
    ensure_status,
)

logger = logging.getLogger(__name__)


class StatusUpdateConflict(RuntimeError):
    pass


def update_reimbursement_status(
    notion_page_id: str,
    expected_old_status: str | None,
    new_status: str,
    requested_by: str | None = None,
    settings=None,
    session_factory=None,
):
    if not new_status:
        raise ValueError("new_status is required")

    init_config()
    settings = settings or load_settings(mode_override="download")
    init_db()
    session_factory = session_factory or SessionLocal
    session: Session = session_factory()
    now = datetime.utcnow()
    action = None

    try:
        record = session.scalar(
            select(ReimbursementRecord).where(
                ReimbursementRecord.notion_page_id == notion_page_id
            )
        )
        if record is None:
            raise ValueError(f"Record not found: {notion_page_id}")
        if record.status != expected_old_status:
            raise StatusUpdateConflict(
                "Local status changed. Please refresh before updating status."
            )

        action = NotionStatusUpdateAction(
            notion_page_id=notion_page_id,
            old_status=record.status,
            new_status=new_status,
            requested_by=requested_by,
            requested_at=now,
            status="pending",
        )
        session.add(action)
        session.commit()
        session.refresh(action)

        notion = create_client(settings.notion_token)
        property_type = get_database_property_type(
            notion,
            settings.notion_page_id,
            settings.status_property_name,
        )
        response = update_page_status(
            notion,
            notion_page_id,
            settings.status_property_name,
            new_status,
            property_type=property_type or "select",
        )

        old_status = record.status
        record.status = new_status
        record.last_synced_at = now
        attachments = session.scalars(
            select(ReimbursementAttachment).where(
                ReimbursementAttachment.notion_page_id == notion_page_id
            )
        ).all()
        record.content_hash = build_content_hash(
            {
                "number": record.number,
                "title": record.title,
                "status": record.status,
                "amount": record.amount,
                "applicant": record.applicant,
                "reimbursed_to": record.reimbursed_to,
                "remark": record.remark,
                "attachments": [
                    {
                        "file_name": item.file_name,
                        "file_type": item.file_type,
                    }
                    for item in attachments
                ],
            }
        )
        ensure_status(session, new_status, now)
        version_data = ReimbursementRecordData(
            notion_page_id=record.notion_page_id,
            notion_url=record.notion_url,
            number=record.number,
            title=record.title,
            status=record.status,
            amount=record.amount,
            applicant=record.applicant,
            reimbursed_to=record.reimbursed_to,
            remark=record.remark,
            attachments=[
                AttachmentData(
                    file_name=item.file_name,
                    file_type=item.file_type,
                    notion_file_url=item.notion_file_url,
                )
                for item in attachments
            ],
            content_hash=record.content_hash,
            notion_created_time=record.notion_created_time,
            notion_last_edited_time=record.notion_last_edited_time,
            raw_properties_json=record.raw_properties_json,
            raw_page_json=None,
        )
        add_version(session, version_data, sync_run_id=None, today=now.date())
        add_status_event(
            session,
            notion_page_id,
            old_status,
            new_status,
            sync_run_id=None,
            today=now.date(),
            now=now,
        )
        action.status = "success"
        action.completed_at = datetime.utcnow()
        action.notion_response_json = json.dumps(response, ensure_ascii=False, default=str)
        session.commit()
        return action
    except Exception as exc:
        logger.exception("Notion status update failed")
        if action is not None:
            action.status = "failed"
            action.completed_at = datetime.utcnow()
            action.error_message = str(exc)
            session.commit()
        raise
    finally:
        session.close()
