"""Shared record-domain primitives used by sync and status updates."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ReimbursementRecordVersion,
    ReimbursementStatus,
    ReimbursementStatusEvent,
)
from app.schemas.reimbursement import ReimbursementRecordData


def build_content_hash(payload: dict) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def ensure_status(session: Session, status_name: str | None, now: datetime) -> None:
    if not status_name:
        return

    for obj in session.new:
        if isinstance(obj, ReimbursementStatus) and obj.status_name == status_name:
            obj.last_seen_at = now
            return

    with session.no_autoflush:
        status = session.scalar(
            select(ReimbursementStatus).where(ReimbursementStatus.status_name == status_name)
        )
    if status:
        status.last_seen_at = now
    else:
        session.add(
            ReimbursementStatus(
                status_name=status_name,
                first_seen_at=now,
                last_seen_at=now,
            )
        )


def next_version_no(session: Session, notion_page_id: str) -> int:
    latest = session.scalar(
        select(func.max(ReimbursementRecordVersion.version_no)).where(
            ReimbursementRecordVersion.notion_page_id == notion_page_id
        )
    )
    return int(latest or 0) + 1


def add_version(
    session: Session,
    data: ReimbursementRecordData,
    sync_run_id: int | None,
    today: date,
) -> None:
    session.add(
        ReimbursementRecordVersion(
            notion_page_id=data.notion_page_id,
            version_no=next_version_no(session, data.notion_page_id),
            snapshot_date=today,
            title=data.title,
            status=data.status,
            amount=data.amount,
            applicant=data.applicant,
            reimbursed_to=data.reimbursed_to,
            remark=data.remark,
            attachment_count=len(data.attachments),
            content_hash=data.content_hash,
            raw_page_json=data.raw_page_json,
            sync_run_id=sync_run_id,
        )
    )


def add_status_event(
    session: Session,
    notion_page_id: str,
    old_status: str | None,
    new_status: str | None,
    sync_run_id: int | None,
    today: date,
    now: datetime,
) -> None:
    session.add(
        ReimbursementStatusEvent(
            notion_page_id=notion_page_id,
            old_status=old_status,
            new_status=new_status,
            changed_date=today,
            detected_at=now,
            sync_run_id=sync_run_id,
        )
    )
