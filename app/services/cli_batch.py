"""Notion-direct CLI batch processing (no local SQLite required)."""

from __future__ import annotations

import logging
import subprocess
import sys

from app.config import check_dependencies, ensure_data_directories, init_config, load_settings
from app.pdf_service import build_pdf_filename

logger = logging.getLogger(__name__)


def process_fapiao(downloaded_items, settings, page_id):
    """Fapiao mode: keep only PDFs, move to fapiao_dir, do not update status."""
    from app.downloader import resolve_download_path
    from app.invoice_to_delivery import default_delivery_excel_path, generate_delivery_excel

    pdf_count = 0
    for item in downloaded_items:
        try:
            if item["type"] != "pdf":
                item["path"].unlink(missing_ok=True)
                continue

            target_path = resolve_download_path(
                settings.fapiao_dir,
                page_id,
                item["path"].name,
            )
            item["path"].replace(target_path)
            logger.info("Saved PDF to fapiao folder: %s", target_path)
            pdf_count += 1
        except Exception as exc:
            logger.warning("Could not handle file %s: %s", item["path"], exc)

    if pdf_count == 0:
        logger.info("No PDF files found for this item.")
        return 0

    try:
        output_path = default_delivery_excel_path(settings.fapiao_dir)
        generate_delivery_excel(settings.fapiao_dir, output_path)
        logger.info("Updated delivery order Excel: %s", output_path)
    except Exception as exc:
        logger.warning("Could not update delivery order Excel: %s", exc)

    return 1


def process_download():
    """Download mode: just download, no PDF generation, no status update."""
    logger.info(
        "Download completed. Skipping PDF generation and status update (MODE=download)."
    )
    return 1


def process_pdf(downloaded_items, settings, number, reimburse_to, name, label_text):
    """PDF mode: generate a single PDF for this page and return its path."""
    from app.pdf_service import create_pdf

    output_path = settings.output_dir / build_pdf_filename(number, reimburse_to, name)
    create_pdf(downloaded_items, output_path, label_text=label_text)
    logger.info("Generated PDF: %s", output_path)

    for item in downloaded_items:
        try:
            item["path"].unlink()
        except Exception as exc:
            logger.warning("Could not remove temp file %s: %s", item["path"], exc)

    return output_path


def run_batch(results, settings):
    """Process a single batch of Notion pages.

    Returns a tuple of (processed_count, generated_pdfs), where generated_pdfs
    is a list of (page_id, pdf_path) for pdf mode.
    """
    from app.downloader import download_media
    from app.notion_client import extract_property_value

    batch_count = 0
    generated_pdfs = []
    for page in results:
        page_id = page["id"]

        number = extract_property_value(page, settings.number_property_name)
        name = extract_property_value(page, settings.name_property_name)
        reimburse_to = extract_property_value(page, settings.reimburse_to_property_name)
        files = extract_property_value(page, settings.files_property_name)

        if number is None or number == "":
            number = "NoNum"
        if not name:
            name = "NoName"
        if not reimburse_to:
            reimburse_to = "mirna"

        label_text = f"{reimburse_to}_{number}_{name}"
        logger.info("Processing: [%s] (%s files)", label_text, len(files) if files else 0)

        if not files:
            logger.info("No files found for %s, skipping download.", name)
            continue

        downloaded_items = download_media(files, settings.download_dir)
        if not downloaded_items:
            logger.warning("Failed to download any valid media.")
            continue

        if settings.mode == "fapiao":
            batch_count += process_fapiao(downloaded_items, settings, page_id)
        elif settings.mode == "download":
            batch_count += process_download()
        else:
            pdf_path = process_pdf(
                downloaded_items,
                settings,
                number,
                reimburse_to,
                name,
                label_text,
            )
            generated_pdfs.append((page_id, pdf_path))
            batch_count += 1

    return batch_count, generated_pdfs


def run_processor(mode_override=None):
    init_config()

    if not check_dependencies():
        return 1

    try:
        settings = load_settings(mode_override=mode_override)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    ensure_data_directories(settings)

    from app.notion_client import create_client, ensure_database_access, query_database_batches

    notion = create_client(settings.notion_token)

    logger.info("Starting Notion Media Processor...")

    try:
        warning = ensure_database_access(notion, settings.notion_page_id)
        if warning:
            logger.warning("%s", warning)

        logger.info(
            "Querying database %s for status '%s'...",
            settings.notion_page_id,
            settings.status_to_process,
        )

        processed_count = 0
        all_generated_pdfs = []

        for results in query_database_batches(settings):
            logger.info("Found %s items to process in this batch.", len(results))
            batch_count, batch_pdfs = run_batch(results, settings)
            processed_count += batch_count
            all_generated_pdfs.extend(batch_pdfs)

        logger.info("Processing complete. %s items processed.", processed_count)

        if settings.mode == "pdf" and all_generated_pdfs:
            from app.notion_client import update_page_status
            from app.pdf_service import merge_pdfs

            merged_path = settings.output_dir / "merged_all.pdf"
            merge_pdfs(
                [pdf_path for _, pdf_path in all_generated_pdfs],
                merged_path,
            )
            logger.info("Generated merged PDF: %s", merged_path)

            logger.info("Updating Notion statuses...")
            logger.warning("Notion API limitations prevent uploading local files.")
            logger.warning("The PDFs have been saved locally.")

            for page_id, _ in all_generated_pdfs:
                try:
                    logger.info(
                        "Updating status for %s to '%s'...",
                        page_id,
                        settings.status_processed,
                    )
                    update_page_status(
                        notion,
                        page_id,
                        settings.status_property_name,
                        settings.status_processed,
                    )
                    logger.info("Status updated successfully.")
                except Exception as exc:
                    logger.error("Error updating status for %s: %s", page_id, exc)

        if processed_count > 0:
            logger.info("Output directory: %s", settings.output_dir)
            if sys.platform == "darwin" and settings.output_dir.exists():
                subprocess.run(["open", str(settings.output_dir)], check=False)
    except Exception as exc:
        logger.error("An error occurred: %s", exc)
        return 1

    return 0
