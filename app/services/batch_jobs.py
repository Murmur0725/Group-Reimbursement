from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from uuid import uuid4

from app.config import init_config, load_settings
from app.db.database import SessionLocal
from app.services.processing import (
    GeneratedFile,
    generate_fapiao_delivery_from_records,
    generate_records_merged_pdf,
)
from app.services.record_queries import get_filtered_records


@dataclass
class BatchJob:
    id: str
    kind: str
    title: str
    status: str = "queued"
    total: int = 0
    processed: int = 0
    skipped: int = 0
    message: str = ""
    files: list[dict] = field(default_factory=list)
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


_JOBS: dict[str, BatchJob] = {}
_LOCK = Lock()


def _now() -> str:
    return datetime.utcnow().isoformat()


def _file_payload(file: GeneratedFile) -> dict:
    return {
        "file_name": file.file_name,
        "file_type": file.file_type,
        "download_url": file.download_url,
        "local_path": str(file.local_path),
    }


def _set_job(job_id: str, **updates):
    with _LOCK:
        job = _JOBS[job_id]
        for key, value in updates.items():
            setattr(job, key, value)
        job.updated_at = _now()


def _append_files(job_id: str, files: list[GeneratedFile]):
    with _LOCK:
        job = _JOBS[job_id]
        job.files = [_file_payload(file) for file in files]
        job.updated_at = _now()


def create_batch_job(kind: str) -> dict:
    title = {
        "pdf": "生成PDF并更新状态",
        "intake": "生成入库信息",
    }.get(kind)
    if title is None:
        raise ValueError(f"Unsupported batch job kind: {kind}")

    job = BatchJob(id=uuid4().hex, kind=kind, title=title)
    with _LOCK:
        _JOBS[job.id] = job
    return get_batch_job(job.id)


def get_batch_job(job_id: str) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return {
            "id": job.id,
            "kind": job.kind,
            "title": job.title,
            "status": job.status,
            "total": job.total,
            "processed": job.processed,
            "skipped": job.skipped,
            "message": job.message,
            "files": list(job.files),
            "error": job.error,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }


def run_batch_job(job_id: str, kind: str):
    try:
        if kind == "pdf":
            _run_pdf_job(job_id)
        elif kind == "intake":
            _run_intake_job(job_id)
        else:
            raise ValueError(f"Unsupported batch job kind: {kind}")
    except Exception as exc:
        _set_job(job_id, status="failed", error=str(exc), message="处理失败。")


def _run_pdf_job(job_id: str):
    init_config()
    pdf_settings = load_settings(mode_override="pdf")
    session = SessionLocal()
    try:
        records = get_filtered_records(session, status=pdf_settings.status_to_process)
        _set_job(
            job_id,
            status="running",
            total=len(records),
            message=f"待处理 {len(records)} 条。",
        )
        if not records:
            _set_job(job_id, status="completed", message="没有待处理条目。")
            return

        def on_progress(*, processed, skipped, phase, total, index):
            message = "正在更新 Notion 状态。" if phase == "status" else "正在生成 PDF。"
            _set_job(
                job_id,
                processed=processed,
                skipped=skipped,
                message=message,
            )

        result = generate_records_merged_pdf(
            session,
            records,
            update_status=True,
            on_progress=on_progress,
            requested_by="web-batch-job-pdf",
        )
        if result.files:
            _append_files(job_id, result.files)
        _set_job(
            job_id,
            status="completed",
            processed=result.processed_count + result.skipped_count,
            skipped=result.skipped_count,
            message=result.message,
        )
    finally:
        session.close()


def _run_intake_job(job_id: str):
    init_config()
    fapiao_settings = load_settings(mode_override="fapiao")
    session = SessionLocal()
    try:
        records = get_filtered_records(session, status=fapiao_settings.status_to_process)
        _set_job(
            job_id,
            status="running",
            total=len(records),
            message=f"待处理 {len(records)} 条。",
        )
        if not records:
            _set_job(job_id, status="completed", message="没有待处理条目。")
            return

        skipped = 0
        latest_files: list[GeneratedFile] = []
        for index, record in enumerate(records, start=1):
            try:
                result = generate_fapiao_delivery_from_records(session, [record])
                if result.files:
                    latest_files = result.files
                else:
                    skipped += 1
            except Exception:
                skipped += 1
            _set_job(
                job_id,
                processed=index,
                skipped=skipped,
                message="正在生成入库信息。",
            )

        if latest_files:
            _append_files(job_id, latest_files)
            message = "入库信息 Excel 已生成。"
        else:
            message = "没有生成入库信息 Excel。"
        _set_job(job_id, status="completed", message=message)
    finally:
        session.close()
