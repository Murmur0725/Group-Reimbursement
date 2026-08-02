"""Shared processing hooks for CLI and backend actions."""

from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cleanup import cleanup_artifacts, clear_all_data
from app.config import init_config, load_settings
from app.db.models import ReimbursementAttachment, ReimbursementRecord
from app.downloader import download_media, resolve_download_path
from app.notion_client import create_client, extract_property_value
from app.pdf_service import build_pdf_filename, create_pdf, merge_pdfs
from app.services.status_update import update_reimbursement_status

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeneratedFile:
    file_name: str
    local_path: Path
    file_type: str
    download_url: str


@dataclass(frozen=True)
class ProcessingResult:
    title: str
    message: str
    files: list[GeneratedFile]
    processed_count: int
    skipped_count: int = 0


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _download_url_for(path: Path) -> str:
    init_config()
    settings = load_settings(mode_override="download")
    resolved = path.resolve()
    buckets = {
        "downloads": settings.download_dir,
        "output_pdfs": settings.output_dir,
        "fapiao": settings.fapiao_dir,
    }
    for bucket, directory in buckets.items():
        try:
            relative = resolved.relative_to(Path(directory).resolve())
        except ValueError:
            continue
        return f"/downloads/{bucket}/{relative.as_posix()}"
    return ""


def _db_attachments_for_record(session: Session, notion_page_id: str) -> list[dict]:
    attachments = session.scalars(
        select(ReimbursementAttachment).where(
            ReimbursementAttachment.notion_page_id == notion_page_id,
            ReimbursementAttachment.notion_file_url.is_not(None),
        )
    ).all()
    return [
        {
            "url": item.notion_file_url,
            "id": item.file_name or item.id,
            "name": item.file_name or str(item.id),
        }
        for item in attachments
        if item.notion_file_url
    ]


def _attachments_for_record(
    session: Session,
    notion_page_id: str,
    settings=None,
    notion=None,
) -> list[dict]:
    if settings is not None and notion is not None:
        try:
            page = notion.pages.retrieve(page_id=notion_page_id)
            files = extract_property_value(page, settings.files_property_name) or []
            if files:
                return files
        except Exception as exc:
            logger.warning(
                "Could not refresh Notion attachments for %s, using local cache: %s",
                notion_page_id,
                exc,
            )

    return _db_attachments_for_record(session, notion_page_id)


def generate_record_pdf(session: Session, notion_page_id: str) -> ProcessingResult:
    init_config()
    settings = load_settings(mode_override="download")
    notion = create_client(settings.notion_token)
    record = session.scalar(
        select(ReimbursementRecord).where(
            ReimbursementRecord.notion_page_id == notion_page_id
        )
    )
    if record is None:
        raise ValueError(f"Record not found: {notion_page_id}")

    media_items = _attachments_for_record(session, notion_page_id, settings, notion)
    if not media_items:
        return ProcessingResult(
            title="生成 PDF",
            message="该记录没有可下载附件。",
            files=[],
            processed_count=0,
            skipped_count=1,
        )

    downloaded_items = download_media(media_items, settings.download_dir)
    if not downloaded_items:
        return ProcessingResult(
            title="生成 PDF",
            message="附件下载失败或没有可识别的 PDF/图片。",
            files=[],
            processed_count=0,
            skipped_count=1,
        )

    output_path = settings.output_dir / build_pdf_filename(
        record.number or "NoNum",
        record.reimbursed_to or "NoReceiver",
        record.title or "NoName",
    )
    label_text = f"{record.reimbursed_to or 'NoReceiver'}_{record.number or 'NoNum'}_{record.title or 'NoName'}"
    create_pdf(downloaded_items, output_path, label_text=label_text)

    return ProcessingResult(
        title="生成 PDF",
        message="单条 PDF 已生成。",
        files=[
            GeneratedFile(
                file_name=output_path.name,
                local_path=output_path,
                file_type="pdf",
                download_url=_download_url_for(output_path),
            )
        ],
        processed_count=1,
    )


def generate_records_merged_pdf(
    session: Session,
    records: list[ReimbursementRecord],
    update_status: bool = False,
    on_progress=None,
    requested_by: str = "web-bulk-pdf",
) -> ProcessingResult:
    init_config()
    settings = load_settings(mode_override="download")
    generated_paths: list[Path] = []
    generated_records: list[ReimbursementRecord] = []
    skipped = 0

    for index, record in enumerate(records, start=1):
        try:
            result = generate_record_pdf(session, record.notion_page_id)
            if result.files:
                generated_paths.append(result.files[0].local_path)
                generated_records.append(record)
            else:
                skipped += 1
        except Exception as exc:
            logger.warning("Could not generate PDF for %s: %s", record.notion_page_id, exc)
            skipped += 1
        if on_progress is not None:
            on_progress(
                processed=len(generated_records) + skipped,
                skipped=skipped,
                phase="pdf",
                total=len(records),
                index=index,
            )

    if not generated_paths:
        return ProcessingResult(
            title="批量生成 PDF",
            message="没有生成任何 PDF。",
            files=[],
            processed_count=0,
            skipped_count=skipped,
        )

    merged_path = settings.output_dir / f"merged_selection_{_timestamp()}.pdf"
    merge_pdfs(generated_paths, merged_path)

    updated_count = 0
    if update_status:
        pdf_settings = load_settings(mode_override="pdf")
        for record in generated_records:
            try:
                update_reimbursement_status(
                    notion_page_id=record.notion_page_id,
                    expected_old_status=record.status,
                    new_status=pdf_settings.status_processed,
                    requested_by=requested_by,
                    settings=pdf_settings,
                )
                updated_count += 1
            except Exception as exc:
                logger.warning(
                    "Could not update status for %s after PDF generation: %s",
                    record.notion_page_id,
                    exc,
                )
                skipped += 1
            if on_progress is not None:
                on_progress(
                    processed=len(generated_records) + skipped,
                    skipped=skipped,
                    phase="status",
                    total=len(records),
                    index=len(generated_records),
                )

    message = "筛选结果合并 PDF 已生成。"
    if update_status:
        message += f" 已更新 {updated_count} 条 Notion 状态。"

    return ProcessingResult(
        title="批量生成 PDF",
        message=message,
        files=[
            GeneratedFile(
                file_name=merged_path.name,
                local_path=merged_path,
                file_type="pdf",
                download_url=_download_url_for(merged_path),
            )
        ],
        processed_count=len(generated_paths),
        skipped_count=skipped,
    )


def generate_fapiao_delivery_from_records(
    session: Session,
    records: list[ReimbursementRecord],
) -> ProcessingResult:
    from app.invoice_to_delivery import default_delivery_excel_path, generate_delivery_excel

    init_config()
    settings = load_settings(mode_override="download")
    notion = create_client(settings.notion_token)
    saved_pdf_count = 0
    skipped = 0

    for record in records:
        media_items = _attachments_for_record(session, record.notion_page_id, settings, notion)
        if not media_items:
            skipped += 1
            continue

        downloaded_items = download_media(media_items, settings.download_dir)
        pdf_items = [item for item in downloaded_items if item.get("type") == "pdf"]
        if not pdf_items:
            skipped += 1
            continue

        for item in pdf_items:
            source = Path(item["path"])
            target = resolve_download_path(
                settings.fapiao_dir,
                record.notion_page_id,
                source.name,
            )
            source.replace(target)
            saved_pdf_count += 1

    if saved_pdf_count == 0:
        return ProcessingResult(
            title="生成入库信息",
            message="没有找到可用于生成入库信息的 PDF 发票。",
            files=[],
            processed_count=0,
            skipped_count=skipped,
        )

    output_path = default_delivery_excel_path(settings.fapiao_dir)
    generate_delivery_excel(settings.fapiao_dir, output_path)
    return ProcessingResult(
        title="生成入库信息",
        message="入库信息 Excel 已生成。",
        files=[
            GeneratedFile(
                file_name=output_path.name,
                local_path=output_path,
                file_type="xlsx",
                download_url=_download_url_for(output_path),
            )
        ],
        processed_count=saved_pdf_count,
        skipped_count=skipped,
    )


def download_attachments_from_records(
    session: Session,
    records: list[ReimbursementRecord],
) -> ProcessingResult:
    init_config()
    settings = load_settings(mode_override="download")
    notion = create_client(settings.notion_token)
    downloaded_files: list[GeneratedFile] = []
    skipped = 0

    for record in records:
        media_items = _attachments_for_record(session, record.notion_page_id, settings, notion)
        if not media_items:
            skipped += 1
            continue

        downloaded_items = download_media(media_items, settings.download_dir)
        if not downloaded_items:
            skipped += 1
            continue

        for item in downloaded_items:
            path = Path(item["path"])
            downloaded_files.append(
                GeneratedFile(
                    file_name=path.name,
                    local_path=path,
                    file_type=item.get("type", "file"),
                    download_url=_download_url_for(path),
                )
            )

    return ProcessingResult(
        title="只下载附件",
        message="附件下载完成，不生成 PDF，也不更新 Notion 状态。",
        files=downloaded_files,
        processed_count=len(downloaded_files),
        skipped_count=skipped,
    )


def cleanup_generated_artifacts() -> ProcessingResult:
    init_config()
    settings = load_settings(mode_override="download")
    existing_dirs = [
        path
        for path in (settings.download_dir, settings.output_dir)
        if Path(path).exists()
    ]
    cleanup_artifacts(settings.download_dir, settings.output_dir)
    return ProcessingResult(
        title="清理临时文件",
        message="downloads 和 output_pdfs 已清理。",
        files=[],
        processed_count=len(existing_dirs),
        skipped_count=0,
    )


def clear_runtime_data() -> ProcessingResult:
    init_config()
    settings = load_settings(mode_override="download")
    subdirs = sorted(p for p in settings.data_dir.iterdir() if p.is_dir())
    item_count = sum(1 for subdir in subdirs for _ in subdir.iterdir())
    return_code = clear_all_data(["--yes"])
    return ProcessingResult(
        title="清空 data",
        message="data 目录下的子目录内容已清空。" if return_code == 0 else "清空 data 时发生错误。",
        files=[],
        processed_count=item_count if return_code == 0 else 0,
        skipped_count=0 if return_code == 0 else item_count,
    )
