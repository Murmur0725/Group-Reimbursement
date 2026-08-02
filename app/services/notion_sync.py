import json
import logging
from datetime import date, datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import init_config, load_settings
from app.db.database import SessionLocal, init_db
from app.db.models import (
    ReimbursementAttachment,
    ReimbursementRecord,
    ReimbursementStatus,
    SyncRun,
)
from app.notion_client import extract_property_value, query_all_database_batches
from app.notion_client import create_client, get_database_property_options
from app.schemas.reimbursement import AttachmentData, ReimbursementRecordData
from app.services.notion_archive import archive_done_record
from app.services.record_domain import (
    add_status_event,
    add_version,
    build_content_hash,
    ensure_status,
)

logger = logging.getLogger(__name__)

# Re-export domain helpers for existing callers/tests.
__all__ = [
    "add_status_event",
    "add_version",
    "apply_record_data",
    "build_content_hash",
    "ensure_status",
    "normalize_notion_page",
    "sync_notion_reimbursements",
]


def parse_notion_datetime(value):
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).replace(tzinfo=None)
    except ValueError:
        return None


def normalize_amount(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_property_with_fallback(page: dict, primary_name: str, fallback_prefix: str, prop_type: str):
    value = extract_property_value(page, primary_name)
    if value is not None:
        return value

    for name, prop in page.get("properties", {}).items():
        if name.startswith(fallback_prefix) and prop.get("type") == prop_type:
            return extract_property_value(page, name)
    return None


def normalize_notion_page(page: dict, settings) -> ReimbursementRecordData:
    files = extract_property_value(page, settings.files_property_name) or []
    attachments = [
        AttachmentData(
            file_name=item.get("name") or item.get("id"),
            file_type=item.get("type"),
            notion_file_url=item.get("url"),
        )
        for item in files
    ]

    number = extract_property_value(page, settings.number_property_name)
    title = extract_property_value(page, settings.name_property_name)
    status = extract_property_value(page, settings.status_property_name)
    amount = normalize_amount(
        extract_property_with_fallback(
            page,
            settings.amount_property_name,
            fallback_prefix="金额",
            prop_type="number",
        )
    )
    applicant = extract_property_value(page, settings.applicant_property_name)
    reimbursed_to = extract_property_value(page, settings.reimburse_to_property_name)
    remark = extract_property_value(page, settings.remark_property_name)

    hash_payload = {
        "number": number,
        "title": title,
        "status": status,
        "amount": amount,
        "applicant": applicant,
        "reimbursed_to": reimbursed_to,
        "remark": remark,
        "attachments": [
            {
                "file_name": item.file_name,
                "file_type": item.file_type,
            }
            for item in attachments
        ],
    }

    return ReimbursementRecordData(
        notion_page_id=page["id"],
        notion_url=page.get("url"),
        number=str(number) if number is not None else None,
        title=title,
        status=status,
        amount=amount,
        applicant=applicant,
        reimbursed_to=reimbursed_to,
        remark=remark,
        attachments=attachments,
        content_hash=build_content_hash(hash_payload),
        notion_created_time=parse_notion_datetime(page.get("created_time")),
        notion_last_edited_time=parse_notion_datetime(page.get("last_edited_time")),
        raw_properties_json=json.dumps(page.get("properties", {}), ensure_ascii=False, default=str),
        raw_page_json=json.dumps(page, ensure_ascii=False, default=str),
    )


def sync_status_options_from_notion(session: Session, settings, now: datetime) -> int:
    notion = create_client(settings.notion_token)
    options = get_database_property_options(
        notion,
        settings.notion_page_id,
        settings.status_property_name,
    )
    for index, option in enumerate(options, start=1):
        status_name = option["name"]
        status = session.scalar(
            select(ReimbursementStatus).where(ReimbursementStatus.status_name == status_name)
        )
        if status:
            status.last_seen_at = now
            status.sort_order = index
        else:
            session.add(
                ReimbursementStatus(
                    status_name=status_name,
                    first_seen_at=now,
                    last_seen_at=now,
                    sort_order=index,
                )
            )
    return len(options)


def upsert_attachments(
    session: Session,
    notion_page_id: str,
    attachments: Iterable[AttachmentData],
    now: datetime,
) -> None:
    for item in attachments:
        existing = session.scalar(
            select(ReimbursementAttachment).where(
                ReimbursementAttachment.notion_page_id == notion_page_id,
                ReimbursementAttachment.file_name == item.file_name,
            )
        )
        if existing:
            existing.last_seen_at = now
            existing.file_type = item.file_type
            existing.notion_file_url = item.notion_file_url
            continue

        session.add(
            ReimbursementAttachment(
                notion_page_id=notion_page_id,
                file_name=item.file_name,
                file_type=item.file_type,
                notion_file_url=item.notion_file_url,
                first_seen_at=now,
                last_seen_at=now,
            )
        )


def apply_record_data(
    session: Session,
    data: ReimbursementRecordData,
    sync_run: SyncRun,
    now: datetime,
    today: date,
) -> str:
    record = session.scalar(
        select(ReimbursementRecord).where(
            ReimbursementRecord.notion_page_id == data.notion_page_id
        )
    )
    ensure_status(session, data.status, now)
    upsert_attachments(session, data.notion_page_id, data.attachments, now)

    if record is None:
        session.add(
            ReimbursementRecord(
                notion_page_id=data.notion_page_id,
                notion_url=data.notion_url,
                number=data.number,
                title=data.title,
                status=data.status,
                amount=data.amount,
                applicant=data.applicant,
                reimbursed_to=data.reimbursed_to,
                remark=data.remark,
                attachment_count=len(data.attachments),
                content_hash=data.content_hash,
                notion_created_time=data.notion_created_time,
                notion_last_edited_time=data.notion_last_edited_time,
                first_synced_at=now,
                last_synced_at=now,
                is_archived=False,
                raw_properties_json=data.raw_properties_json,
            )
        )
        add_version(session, data, sync_run.id, today)
        if data.status:
            add_status_event(session, data.notion_page_id, None, data.status, sync_run.id, today, now)
            sync_run.status_event_count += 1
        sync_run.created_count += 1
        return "created"

    old_status = record.status
    old_hash = record.content_hash
    record.notion_url = data.notion_url
    record.number = data.number
    record.title = data.title
    record.status = data.status
    record.amount = data.amount
    record.applicant = data.applicant
    record.reimbursed_to = data.reimbursed_to
    record.remark = data.remark
    record.attachment_count = len(data.attachments)
    record.content_hash = data.content_hash
    record.notion_created_time = data.notion_created_time
    record.notion_last_edited_time = data.notion_last_edited_time
    record.last_synced_at = now
    record.is_archived = False
    record.raw_properties_json = data.raw_properties_json

    if old_status != data.status:
        add_status_event(session, data.notion_page_id, old_status, data.status, sync_run.id, today, now)
        sync_run.status_event_count += 1

    if old_hash != data.content_hash:
        add_version(session, data, sync_run.id, today)
        sync_run.updated_count += 1
        return "updated"

    sync_run.unchanged_count += 1
    return "unchanged"


def mark_missing_archived(session: Session, seen_page_ids: set[str], now: datetime) -> None:
    if not seen_page_ids:
        return
    records = session.scalars(
        select(ReimbursementRecord).where(
            ReimbursementRecord.is_archived.is_(False),
            ReimbursementRecord.notion_page_id.not_in(seen_page_ids),
        )
    ).all()
    for record in records:
        record.is_archived = True
        record.last_synced_at = now


def sync_notion_reimbursements(mode: str = "manual", settings=None, session_factory=None):
    init_config()
    settings = settings or load_settings(mode_override="download")
    init_db()
    session_factory = session_factory or SessionLocal
    session = session_factory()
    now = datetime.utcnow()
    today = now.date()
    sync_run = SyncRun(mode=mode, started_at=now, status="running")
    session.add(sync_run)
    session.commit()
    session.refresh(sync_run)

    seen_page_ids: set[str] = set()
    try:
        sync_status_options_from_notion(session, settings, now)
        for batch in query_all_database_batches(settings):
            sync_run.fetched_count += len(batch)
            for page in batch:
                data = normalize_notion_page(page, settings)
                seen_page_ids.add(data.notion_page_id)
                apply_record_data(session, data, sync_run, now, today)
                archive_action = archive_done_record(session, data, settings=settings)
                if archive_action and archive_action.status == "success":
                    record = session.scalar(
                        select(ReimbursementRecord).where(
                            ReimbursementRecord.notion_page_id == data.notion_page_id
                        )
                    )
                    if record:
                        record.is_archived = True
        mark_missing_archived(session, seen_page_ids, now)
        sync_run.status = "success"
        sync_run.finished_at = datetime.utcnow()
        session.commit()
        return sync_run
    except Exception as exc:
        logger.exception("Notion reimbursement sync failed")
        session.rollback()
        failed_run = session.get(SyncRun, sync_run.id)
        if failed_run:
            failed_run.status = "failed"
            failed_run.error_message = str(exc)
            failed_run.finished_at = datetime.utcnow()
            session.commit()
        raise
    finally:
        session.close()
