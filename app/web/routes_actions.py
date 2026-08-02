from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.batch_jobs import create_batch_job, get_batch_job, run_batch_job
from app.services.processing import (
    cleanup_generated_artifacts,
    clear_runtime_data,
    download_attachments_from_records,
    generate_fapiao_delivery_from_records,
    generate_record_pdf,
    generate_records_merged_pdf,
)
from app.services.record_queries import get_filtered_records
from app.services.status_update import update_reimbursement_status
from app.web.templates import templates

router = APIRouter(prefix="/actions")


@router.post("/batch-jobs/{kind}")
def start_batch_job(kind: str, background_tasks: BackgroundTasks):
    if kind not in {"pdf", "intake"}:
        raise HTTPException(status_code=404, detail="Unknown batch job kind")
    job = create_batch_job(kind)
    background_tasks.add_task(run_batch_job, job["id"], kind)
    return job


@router.get("/batch-jobs/{job_id}")
def batch_job_status(job_id: str):
    try:
        return get_batch_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Batch job not found") from exc


@router.post("/status-update")
def status_update(
    notion_page_id: str = Form(...),
    expected_old_status: str = Form(""),
    new_status: str = Form(...),
    redirect_to: str = Form(""),
):
    old_status = expected_old_status or None
    redirect_url = redirect_to or f"/records/{notion_page_id}"
    if old_status == new_status:
        return RedirectResponse(redirect_url, status_code=303)
    update_reimbursement_status(
        notion_page_id=notion_page_id,
        expected_old_status=old_status,
        new_status=new_status,
        requested_by="system",
    )
    return RedirectResponse(redirect_url, status_code=303)


@router.post("/generate-record-pdf")
def generate_record_pdf_action(
    request: Request,
    notion_page_id: str = Form(...),
    db: Session = Depends(get_db),
):
    result = generate_record_pdf(db, notion_page_id)
    return templates.TemplateResponse(
        request,
        "processing_result.html",
        {"result": result},
    )


def _records_from_filters(
    db: Session,
    status: str | None,
    applicant: str | None,
    reimbursed_to: str | None,
    q: str | None,
    amount: str | float | None,
    tolerance: float,
):
    parsed_amount = None
    if amount not in (None, ""):
        parsed_amount = float(amount)
    return get_filtered_records(
        db,
        status=status or None,
        applicant=applicant or None,
        reimbursed_to=reimbursed_to or None,
        q=q or None,
        amount=parsed_amount,
        tolerance=tolerance,
    )


@router.post("/generate-filtered-pdf")
def generate_filtered_pdf_action(
    request: Request,
    status: str = Form(""),
    applicant: str = Form(""),
    reimbursed_to: str = Form(""),
    q: str = Form(""),
    amount: str = Form(""),
    tolerance: float = Form(0),
    update_status: bool = Form(False),
    db: Session = Depends(get_db),
):
    records = _records_from_filters(db, status, applicant, reimbursed_to, q, amount, tolerance)
    result = generate_records_merged_pdf(db, records, update_status=update_status)
    return templates.TemplateResponse(
        request,
        "processing_result.html",
        {"result": result},
    )


@router.post("/generate-delivery-excel")
def generate_delivery_excel_action(
    request: Request,
    status: str = Form(""),
    applicant: str = Form(""),
    reimbursed_to: str = Form(""),
    q: str = Form(""),
    amount: str = Form(""),
    tolerance: float = Form(0),
    db: Session = Depends(get_db),
):
    records = _records_from_filters(db, status, applicant, reimbursed_to, q, amount, tolerance)
    result = generate_fapiao_delivery_from_records(db, records)
    return templates.TemplateResponse(
        request,
        "processing_result.html",
        {"result": result},
    )


@router.post("/download-attachments")
def download_attachments_action(
    request: Request,
    status: str = Form(""),
    applicant: str = Form(""),
    reimbursed_to: str = Form(""),
    q: str = Form(""),
    amount: str = Form(""),
    tolerance: float = Form(0),
    db: Session = Depends(get_db),
):
    records = _records_from_filters(db, status, applicant, reimbursed_to, q, amount, tolerance)
    result = download_attachments_from_records(db, records)
    return templates.TemplateResponse(
        request,
        "processing_result.html",
        {"result": result},
    )


@router.post("/cleanup-artifacts")
def cleanup_artifacts_action(request: Request):
    result = cleanup_generated_artifacts()
    return templates.TemplateResponse(
        request,
        "processing_result.html",
        {"result": result},
    )


@router.post("/clear-data")
def clear_data_action(request: Request):
    result = clear_runtime_data()
    return templates.TemplateResponse(
        request,
        "processing_result.html",
        {"result": result},
    )
