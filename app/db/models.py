from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ReimbursementRecord(Base):
    __tablename__ = "reimbursement_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notion_page_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    notion_url: Mapped[str | None] = mapped_column(String, nullable=True)
    number: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    applicant: Mapped[str | None] = mapped_column(String, nullable=True)
    reimbursed_to: Mapped[str | None] = mapped_column(String, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_count: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String, index=True)
    notion_created_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notion_last_edited_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    raw_properties_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReimbursementRecordVersion(Base):
    __tablename__ = "reimbursement_record_versions"
    __table_args__ = (
        UniqueConstraint("notion_page_id", "version_no", name="uq_record_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notion_page_id: Mapped[str] = mapped_column(String, index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    snapshot_date: Mapped[date] = mapped_column(Date)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    applicant: Mapped[str | None] = mapped_column(String, nullable=True)
    reimbursed_to: Mapped[str | None] = mapped_column(String, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_count: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String, index=True)
    raw_page_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReimbursementStatusEvent(Base):
    __tablename__ = "reimbursement_status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notion_page_id: Mapped[str] = mapped_column(String, index=True)
    old_status: Mapped[str | None] = mapped_column(String, nullable=True)
    new_status: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    changed_date: Mapped[date] = mapped_column(Date, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sync_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)


class ReimbursementStatus(Base):
    __tablename__ = "reimbursement_statuses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status_name: Mapped[str] = mapped_column(String, unique=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String, default="manual")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="running", index=True)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0)
    status_event_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReimbursementAttachment(Base):
    __tablename__ = "reimbursement_attachments"
    __table_args__ = (
        UniqueConstraint("notion_page_id", "file_name", "notion_file_url", name="uq_attachment_file"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notion_page_id: Mapped[str] = mapped_column(String, index=True)
    file_name: Mapped[str | None] = mapped_column(String, nullable=True)
    file_type: Mapped[str | None] = mapped_column(String, nullable=True)
    notion_file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_path: Mapped[str | None] = mapped_column(String, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_downloaded: Mapped[bool] = mapped_column(Boolean, default=False)


class NotionStatusUpdateAction(Base):
    __tablename__ = "notion_status_update_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notion_page_id: Mapped[str] = mapped_column(String, index=True)
    old_status: Mapped[str | None] = mapped_column(String, nullable=True)
    new_status: Mapped[str] = mapped_column(String)
    requested_by: Mapped[str | None] = mapped_column(String, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    notion_response_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class NotionDoneArchiveAction(Base):
    __tablename__ = "notion_done_archive_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notion_page_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    archive_page_id: Mapped[str] = mapped_column(String, index=True)
    status_name: Mapped[str | None] = mapped_column(String, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
