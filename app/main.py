import sys

from app.cleanup import cleanup_artifacts, clear_all_data
from app.logging_config import setup_logging


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


def should_start_web(argv):
    if not argv:
        return False
    first = argv[0].lower()
    return first in ("web", "server", "backend")


def run_web_server(host="127.0.0.1", port=8000):
    """Start the local reimbursement backend."""
    try:
        import uvicorn
    except ModuleNotFoundError:
        print("[ERROR] Missing dependency: uvicorn")
        print("Install dependencies with:")
        print("  uv sync")
        return 1

    uvicorn.run("app.web.app:app", host=host, port=port)
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
        ("7", ["web"], "web", "启动本地报销后台"),
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

    setup_logging()

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
        from app.invoice_to_delivery import delivery_main

        return delivery_main(args[1:])

    if should_start_web(args):
        return run_web_server()

    mode_override = None
    if args:
        candidate = args[0].lower()
        if candidate in ("pdf", "download", "fapiao"):
            mode_override = candidate

    from app.services.cli_batch import run_processor

    return run_processor(mode_override=mode_override)


if __name__ == "__main__":
    raise SystemExit(main())
