import subprocess
import sys

from app.cleanup import cleanup_artifacts, clear_all_data
from app.config import check_dependencies, ensure_data_directories, load_settings


def should_cleanup(argv):
    if not argv:
        return False

    first = argv[0].lower()
    combined = " ".join(argv).lower().replace(" ", "")
    return first in ("clear", "cleanup", "clearup") or combined in ("clear", "cleanup", "clearup")


def should_generate_delivery(argv):
    if not argv:
        return False
    first = argv[0].lower()
    return first in ("invoice-to-delivery", "delivery", "fapiao-table")


def build_pdf_filename(number, reimburse_to, name):
    filename = f"{reimburse_to}_{number}_{name}.pdf"
    forbidden = set("/\\:*?\"<>|")
    sanitized = "".join(char for char in filename if char not in forbidden).strip()
    return sanitized or "output.pdf"


def _process_fapiao(downloaded_items, settings, page_id):
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
            print(f"  Saved PDF to fapiao folder: {target_path}")
            pdf_count += 1
        except Exception as exc:
            print(f"  Warning: Could not handle file {item['path']}: {exc}")

    if pdf_count == 0:
        print("  No PDF files found for this item.")
        return 0

    # Auto-generate the delivery-order Excel after saving new fapiao PDFs.
    try:
        output_path = default_delivery_excel_path(settings.fapiao_dir)
        generate_delivery_excel(settings.fapiao_dir, output_path)
        print(f"  Updated delivery order Excel: {output_path}")
    except Exception as exc:
        print(f"  Warning: Could not update delivery order Excel: {exc}")

    return 1


def _process_download():
    """Download mode: just download, no PDF generation, no status update."""
    print(
        "  Download completed. Skipping PDF generation and status update "
        "(MODE=download)."
    )
    return 1


def _process_pdf(downloaded_items, settings, number, reimburse_to, name, label_text):
    """PDF mode: generate a single PDF for this page and return its path."""
    from app.pdf_service import create_pdf

    output_path = settings.output_dir / build_pdf_filename(number, reimburse_to, name)
    create_pdf(downloaded_items, output_path, label_text=label_text)
    print(f"  Generated PDF: {output_path}")

    for item in downloaded_items:
        try:
            item["path"].unlink()
        except Exception as exc:
            print(f"  Warning: Could not remove temp file {item['path']}: {exc}")

    return output_path


def _run_batch(results, settings, notion):
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
            pdf_path = _process_pdf(
                downloaded_items, settings,
                number, reimburse_to, name, label_text,
            )
            generated_pdfs.append((page_id, pdf_path))
            batch_count += 1

    return batch_count, generated_pdfs


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
        all_generated_pdfs = []

        for results in query_database_batches(settings):
            print(f"Found {len(results)} items to process in this batch.")
            batch_count, batch_pdfs = _run_batch(results, settings, notion)
            processed_count += batch_count
            all_generated_pdfs.extend(batch_pdfs)

        print(f"\nProcessing complete. {processed_count} items processed.")

        if settings.mode == "pdf" and all_generated_pdfs:
            from app.pdf_service import merge_pdfs
            from app.notion_client import update_page_status

            merged_path = settings.output_dir / "merged_all.pdf"
            merge_pdfs(
                [pdf_path for _, pdf_path in all_generated_pdfs],
                merged_path,
            )
            print(f"Generated merged PDF: {merged_path}")

            print("\nUpdating Notion statuses...")
            print("  [WARNING] Notion API limitations prevent uploading local files.")
            print("            The PDFs have been saved locally.")

            for page_id, _ in all_generated_pdfs:
                try:
                    print(
                        f"  Updating status for {page_id} to "
                        f"'{settings.status_processed}'..."
                    )
                    update_page_status(
                        notion,
                        page_id,
                        settings.status_property_name,
                        settings.status_processed,
                    )
                    print("  Status updated successfully.")
                except Exception as exc:
                    print(f"  Error updating status for {page_id}: {exc}")

        if processed_count > 0:
            print(f"\nOutput directory: {settings.output_dir}")
            if sys.platform == "darwin" and settings.output_dir.exists():
                subprocess.run(["open", str(settings.output_dir)], check=False)
    except Exception as exc:
        print(f"An error occurred: {exc}")
        return 1

    return 0


def interactive_menu():
    """Display an interactive menu and return the chosen command args.

    Returns None if the user chooses to quit. For the clear-data action,
    returns a sentinel string that main() handles directly.
    """
    menu_items = [
        ("0", None, "quit", "退出"),
        ("1", ["pdf"], "pdf", "下载附件并生成合并 PDF，更新 Notion 状态"),
        ("2", ["fapiao"], "fapiao", "下载发票 PDF 并生成发货单 Excel"),
        ("3", ["download"], "download", "只下载附件，不生成 PDF"),
        ("4", ["cleanup"], "cleanup", "清理 downloads 和 output_pdfs"),
        ("5", "__clear_data__", "clear-data", "清空整个 data 目录"),
        ("6", ["invoice-to-delivery"], "invoice-to-delivery", "从现有发票生成发货单 Excel"),
    ]

    print("\nNotion 报销工具")
    print("=" * 60)
    for number, _, name, description in menu_items:
        print(f"  {number}. {name:<22} - {description}")

    while True:
        try:
            choice = input("\n请选择功能（输入数字或名称）：").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return None

        if not choice:
            continue

        for number, args, name, _ in menu_items:
            if choice == number or choice == name:
                return args

        print(f"无效选择：{choice}，请重新输入。")


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv

    if not args:
        menu_result = interactive_menu()
        if menu_result is None:
            return 0
        if menu_result == "__clear_data__":
            return clear_all_data(["--yes"])
        args = menu_result

    if should_cleanup(args):
        cleanup_artifacts()
        return 0

    if should_generate_delivery(args):
        from app.invoice_to_delivery import main as delivery_main
        return delivery_main(args[1:])

    mode_override = None
    if args:
        candidate = args[0].lower()
        if candidate in ("pdf", "download", "fapiao"):
            mode_override = candidate

    return run_processor(mode_override=mode_override)


if __name__ == "__main__":
    raise SystemExit(main())
