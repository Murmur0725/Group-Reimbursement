from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.config import init_config, load_settings
from app.db.database import get_db
from app.db.models import (
    ReimbursementAttachment,
    ReimbursementRecord,
    ReimbursementRecordVersion,
    ReimbursementStatus,
    ReimbursementStatusEvent,
)
from app.services.record_queries import get_filtered_records
from app.web.templates import templates

router = APIRouter(prefix="/records")


def _format_file_size(size: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024
    return f"{size} B"


def _data_file_summary(settings):
    buckets = [
        ("downloads", "downloads", settings.download_dir),
        ("output_pdfs", "output_pdfs", settings.output_dir),
        ("fapiao", "fapiao", settings.fapiao_dir),
    ]
    summary = []
    total_count = 0
    for key, label, directory in buckets:
        files = []
        if directory.exists():
            paths = sorted(
                (path for path in directory.rglob("*") if path.is_file()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            for path in paths:
                relative = path.relative_to(directory).as_posix()
                files.append(
                    {
                        "name": relative,
                        "size": _format_file_size(path.stat().st_size),
                        "url": f"/downloads/{key}/{quote(relative, safe='/')}",
                    }
                )
        total_count += len(files)
        summary.append({"label": label, "count": len(files), "files": files})
    return {"total_count": total_count, "buckets": summary}


@router.get("")
def records_list(
    request: Request,
    status: str | None = None,
    applicant: str | None = None,
    reimbursed_to: str | None = None,
    q: str | None = None,
    amount: str | None = Query(default=None),
    tolerance: float = Query(default=0, ge=0, le=2),
    db: Session = Depends(get_db),
):
    # Parse amount: convert empty string to None, otherwise try to parse as float
    parsed_amount: float | None = None
    if amount is not None and amount.strip() != "":
        try:
            parsed_amount = float(amount)
        except ValueError:
            parsed_amount = None
    
    records = get_filtered_records(
        db,
        status=status,
        applicant=applicant,
        reimbursed_to=reimbursed_to,
        q=q,
        amount=parsed_amount,
        tolerance=tolerance,
    )

    latest_event_rows = db.execute(
        select(
            ReimbursementStatusEvent.notion_page_id,
            func.max(ReimbursementStatusEvent.changed_date),
        ).group_by(ReimbursementStatusEvent.notion_page_id)
    ).all()
    latest_status_dates = {
        notion_page_id: latest_date for notion_page_id, latest_date in latest_event_rows
    }
    statuses = db.scalars(
        select(ReimbursementStatus).order_by(
            ReimbursementStatus.sort_order.is_(None),
            ReimbursementStatus.sort_order,
            ReimbursementStatus.status_name,
        )
    ).all()
    init_config()
    pdf_settings = load_settings(mode_override="pdf")
    fapiao_settings = load_settings(mode_override="fapiao")
    data_settings = load_settings(mode_override="download")
    applicants = db.scalars(
        select(ReimbursementRecord.applicant)
        .where(
            ReimbursementRecord.is_archived.is_(False),
            ReimbursementRecord.applicant.is_not(None),
            ReimbursementRecord.applicant != "",
        )
        .distinct()
        .order_by(ReimbursementRecord.applicant)
    ).all()
    reimbursed_to_options = db.scalars(
        select(ReimbursementRecord.reimbursed_to)
        .where(
            ReimbursementRecord.is_archived.is_(False),
            ReimbursementRecord.reimbursed_to.is_not(None),
            ReimbursementRecord.reimbursed_to != "",
        )
        .distinct()
        .order_by(ReimbursementRecord.reimbursed_to)
    ).all()
    return templates.TemplateResponse(
        request,
        "records_list.html",
        {
            "records": records,
            "statuses": statuses,
            "pdf_status": pdf_settings.status_to_process,
            "pdf_status_processed": pdf_settings.status_processed,
            "fapiao_status": fapiao_settings.status_to_process,
            "pdf_pending_count": len(
                get_filtered_records(db, status=pdf_settings.status_to_process)
            ),
            "fapiao_pending_count": len(
                get_filtered_records(db, status=fapiao_settings.status_to_process)
            ),
            "data_file_summary": _data_file_summary(data_settings),
            "applicants": applicants,
            "reimbursed_to_options": reimbursed_to_options,
            "latest_status_dates": latest_status_dates,
            "selected_status": status,
            "selected_applicant": applicant,
            "selected_reimbursed_to": reimbursed_to,
            "q": q or "",
            "amount": amount,
            "tolerance": tolerance,
        },
    )


@router.get("/{notion_page_id}")
def record_detail(
    notion_page_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    record = db.scalar(
        select(ReimbursementRecord).where(
            ReimbursementRecord.notion_page_id == notion_page_id
        )
    )
    events = db.scalars(
        select(ReimbursementStatusEvent)
        .where(ReimbursementStatusEvent.notion_page_id == notion_page_id)
        .order_by(ReimbursementStatusEvent.changed_date, ReimbursementStatusEvent.id)
    ).all()
    versions = db.scalars(
        select(ReimbursementRecordVersion)
        .where(ReimbursementRecordVersion.notion_page_id == notion_page_id)
        .order_by(desc(ReimbursementRecordVersion.version_no))
    ).all()
    attachments = db.scalars(
        select(ReimbursementAttachment).where(
            ReimbursementAttachment.notion_page_id == notion_page_id
        )
    ).all()
    statuses = db.scalars(
        select(ReimbursementStatus).order_by(
            ReimbursementStatus.sort_order.is_(None),
            ReimbursementStatus.sort_order,
            ReimbursementStatus.status_name,
        )
    ).all()
    return templates.TemplateResponse(
        request,
        "record_detail.html",
        {
            "record": record,
            "events": events,
            "versions": versions,
            "attachments": attachments,
            "statuses": statuses,
        },
    )
