import subprocess
import sys

from app.cleanup import cleanup_artifacts
from app.config import check_dependencies, ensure_data_directories, load_settings


def should_cleanup(argv):
    if not argv:
        return False

    first = argv[0].lower()
    combined = " ".join(argv).lower().replace(" ", "")
    return first in ("clear", "cleanup", "clearup") or combined in ("clear", "cleanup", "clearup")


def build_pdf_filename(number, reimburse_to, name):
    filename = f"{number}_{reimburse_to}_{name}.pdf"
    sanitized = "".join(
        char for char in filename if char.isalnum() or char in (" ", ".", "_", "-")
    ).strip()
    return sanitized or "output.pdf"


def _process_fapiao(downloaded_items, settings, page_id):
    """Fapiao mode: keep only PDFs, move to fapiao_dir, do not update status."""
    from app.downloader import resolve_download_path

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
            print(f"  Saved PDF to fapiao folder: {target_path}")
            pdf_count += 1
        except Exception as exc:
            print(f"  Warning: Could not handle file {item['path']}: {exc}")

    if pdf_count == 0:
        print("  No PDF files found for this item.")
        return 0
    return 1


def _process_download():
    """Download mode: just download, no PDF generation, no status update."""
    print(
        "  Download completed. Skipping PDF generation and status update "
        "(MODE=download)."
    )
    return 1


def _process_pdf(downloaded_items, settings, notion, page_id, number, reimburse_to, name, label_text):
    """PDF mode: generate PDF with label, update Notion status."""
    from app.notion_client import update_page_status
    from app.pdf_service import create_pdf

    output_path = settings.output_dir / build_pdf_filename(number, reimburse_to, name)
    create_pdf(downloaded_items, output_path, label_text=label_text)
    print(f"  Generated PDF: {output_path}")

    for item in downloaded_items:
        try:
            item["path"].unlink()
        except Exception as exc:
            print(f"  Warning: Could not remove temp file {item['path']}: {exc}")

    print("  [WARNING] Notion API limitations prevent uploading local files.")
    print("            The PDF has been saved locally.")

    try:
        print(f"  Updating status to '{settings.status_processed}'...")
        update_page_status(
            notion,
            page_id,
            settings.status_property_name,
            settings.status_processed,
        )
        print("  Status updated successfully.")
        return 1
    except Exception as exc:
        print(f"  Error updating status: {exc}")
        return 0


def _run_batch(results, settings, notion):
    """Process a single batch of Notion pages. Returns count of processed items."""
    from app.downloader import download_media
    from app.notion_client import extract_property_value

    batch_count = 0
    for page in results:
        page_id = page["id"]
        number = extract_property_value(page, settings.number_property_name)
        name = extract_property_value(page, settings.name_property_name)
        reimburse_to = extract_property_value(page, settings.reimburse_to_property_name)
        files = extract_property_value(page, settings.files_property_name)

        if number is None:
            number = "NoNum"
        if not name:
            name = "NoName"
        if not reimburse_to:
            reimburse_to = "Unknown"

        label_text = f"{number}_{reimburse_to}_{name}"
        print(f"Processing: [{label_text}] ({len(files) if files else 0} files)")

        if not files:
            print(f"  No files found for {name}, skipping download.")
            continue

        downloaded_items = download_media(files, settings.download_dir)
        if not downloaded_items:
            print("  Failed to download any valid media.")
            continue

        if settings.mode == "fapiao":
            batch_count += _process_fapiao(downloaded_items, settings, page_id)
        elif settings.mode == "download":
            batch_count += _process_download()
        else:
            batch_count += _process_pdf(
                downloaded_items, settings, notion, page_id,
                number, reimburse_to, name, label_text,
            )

    return batch_count


def run_processor(mode_override=None):
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

    print("Starting Notion Media Processor...")

    try:
        warning = ensure_database_access(notion, settings.notion_page_id)
        if warning:
            print(warning)

        print(
            f"Querying database {settings.notion_page_id} for status "
            f"'{settings.status_to_process}'..."
        )

        processed_count = 0

        for results in query_database_batches(settings):
            print(f"Found {len(results)} items to process in this batch.")
            processed_count += _run_batch(results, settings, notion)

        print(f"\nProcessing complete. {processed_count} items processed.")

        if processed_count > 0:
            print(f"\nOutput directory: {settings.output_dir}")
            if sys.platform == "darwin" and settings.output_dir.exists():
                subprocess.run(["open", str(settings.output_dir)], check=False)
    except Exception as exc:
        print(f"An error occurred: {exc}")
        return 1

    return 0


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv

    if should_cleanup(args):
        cleanup_artifacts()
        return 0

    mode_override = None
    if args:
        candidate = args[0].lower()
        if candidate in ("pdf", "download", "fapiao"):
            mode_override = candidate

    return run_processor(mode_override=mode_override)


if __name__ == "__main__":
    raise SystemExit(main())
