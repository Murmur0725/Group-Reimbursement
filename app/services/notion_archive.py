import logging
import os
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import load_settings
from app.db.models import NotionDoneArchiveAction
from app.notion_client import create_client, normalize_database_id
from app.schemas.reimbursement import ReimbursementRecordData

logger = logging.getLogger(__name__)

DEFAULT_ARCHIVE_PAGE_ID = "2d199adbdb7b808186e2c7c9663eb8a9"


def done_archive_enabled() -> bool:
    return os.getenv("ENABLE_NOTION_DONE_ARCHIVE", "0") == "1"


def get_done_status_name() -> str:
    return os.getenv("NOTION_DONE_STATUS_NAME", "done")


def get_archive_page_id() -> str:
    return os.getenv("NOTION_DONE_ARCHIVE_PAGE_ID", DEFAULT_ARCHIVE_PAGE_ID)


def is_done_status(status: str | None) -> bool:
    if not status:
        return False
    return status.strip().lower() == get_done_status_name().strip().lower()


def _text_rich(text: str):
    return [{"type": "text", "text": {"content": text[:2000]}}]


def _archive_blocks(data: ReimbursementRecordData):
    title = data.title or "未命名报销单"
    amount = "" if data.amount is None else f"{data.amount:.2f}"
    lines = [
        f"编号：{data.number or ''}",
        f"状态：{data.status or ''}",
        f"金额：{amount}",
        f"申请人：{data.applicant or ''}",
        f"报销给谁：{data.reimbursed_to or ''}",
        f"备注：{data.remark or ''}",
        f"原 Notion 页面：{data.notion_url or data.notion_page_id}",
    ]
    if data.attachments:
        lines.append("附件：")
        lines.extend(f"- {item.file_name or item.notion_file_url or ''}" for item in data.attachments)

    return [
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": _text_rich(title)},
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": _text_rich("\n".join(lines))},
        },
    ]


def archive_done_record(
    session: Session,
    data: ReimbursementRecordData,
    settings=None,
) -> NotionDoneArchiveAction | None:
    if not done_archive_enabled() or not is_done_status(data.status):
        return None

    existing = session.scalar(
        select(NotionDoneArchiveAction).where(
            NotionDoneArchiveAction.notion_page_id == data.notion_page_id
        )
    )
    if existing and existing.status == "success":
        return existing

    settings = settings or load_settings(mode_override="download")
    archive_page_id = normalize_database_id(get_archive_page_id())
    action = existing or NotionDoneArchiveAction(
        notion_page_id=data.notion_page_id,
        archive_page_id=archive_page_id,
        status_name=data.status,
        requested_at=datetime.utcnow(),
        status="pending",
    )
    if existing is None:
        session.add(action)
        session.flush()

    notion = create_client(settings.notion_token)
    try:
        notion.blocks.children.append(
            block_id=archive_page_id,
            children=_archive_blocks(data),
        )
        notion.pages.update(page_id=data.notion_page_id, archived=True)
        action.status = "success"
        action.completed_at = datetime.utcnow()
        action.error_message = None
        logger.info("Archived done Notion page %s", data.notion_page_id)
        return action
    except Exception as exc:
        action.status = "failed"
        action.completed_at = datetime.utcnow()
        action.error_message = str(exc)
        logger.error("Could not archive done Notion page %s: %s", data.notion_page_id, exc)
        raise

