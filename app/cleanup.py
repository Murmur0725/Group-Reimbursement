import argparse
import logging
import shutil
from pathlib import Path

from app.config import DATA_DIR, DOWNLOAD_DIR, OUTPUT_DIR

logger = logging.getLogger(__name__)


def cleanup_artifacts(download_dir=DOWNLOAD_DIR, output_dir=OUTPUT_DIR):
    removed_any = False

    for path in (download_dir, output_dir):
        if path.exists():
            shutil.rmtree(path)
            logger.info("Removed %s", path)
            removed_any = True

    if not removed_any:
        logger.info("No data/downloads or data/output_pdfs directory to remove.")


def clear_directory(directory: Path, dry_run: bool = False) -> int:
    """删除目录下的所有文件和子目录，保留目录本身。"""
    removed_count = 0
    if not directory.exists():
        print(f"  目录不存在，跳过: {directory}")
        return removed_count

    for item in sorted(directory.iterdir()):
        if dry_run:
            logger.info("  [预览] 将删除: %s", item)
            removed_count += 1
            continue

        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            logger.info("  已删除: %s", item)
            removed_count += 1
        except Exception as exc:
            logger.error("  [错误] 无法删除 %s: %s", item, exc)

    return removed_count


def clear_all_data(argv: list[str] | None = None) -> int:
    """清空 data/ 目录下的所有内容，但保留 data/ 目录本身。"""
    parser = argparse.ArgumentParser(
        description="清空 data/ 目录下的所有内容（保留 data/ 目录本身）。"
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="跳过确认，直接删除",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只预览会删除哪些内容，不真正删除",
    )
    args = parser.parse_args(argv)

    if not DATA_DIR.exists():
        logger.error("[错误] data 目录不存在: %s", DATA_DIR)
        return 1

    subdirs = sorted(p for p in DATA_DIR.iterdir() if p.is_dir())
    if not subdirs:
        logger.info("data 目录下没有子目录: %s", DATA_DIR)
        return 0

    logger.info("将清空以下目录的内容：")
    for subdir in subdirs:
        logger.info("  - %s", subdir)

    if args.dry_run:
        logger.info("\n[预览模式] 不会真正删除任何文件。\n")
    elif not args.yes:
        try:
            answer = input("\n确认清空？(yes/no): ")
        except (EOFError, KeyboardInterrupt):
            logger.info("\n已取消")
            return 130
        if answer.strip().lower() not in ("yes", "y"):
            logger.info("已取消")
            return 0
        logger.info("")

    total = 0
    for subdir in subdirs:
        logger.info("清理: %s", subdir)
        total += clear_directory(subdir, dry_run=args.dry_run)

    action = "将删除" if args.dry_run else "已删除"
    logger.info("\n%s %s 个项目", action, total)
    return 0
