from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class AttachmentData:
    file_name: str | None
    file_type: str | None
    notion_file_url: str | None


@dataclass(frozen=True)
class ReimbursementRecordData:
    notion_page_id: str
    notion_url: str | None
    number: str | None
    title: str | None
    status: str | None
    amount: float | None
    applicant: str | None
    reimbursed_to: str | None
    remark: str | None
    attachments: list[AttachmentData] = field(default_factory=list)
    content_hash: str = ""
    notion_created_time: datetime | None = None
    notion_last_edited_time: datetime | None = None
    raw_properties_json: str | None = None
    raw_page_json: str | None = None

