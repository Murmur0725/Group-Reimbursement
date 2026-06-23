import argparse
import shutil
import sys
from pathlib import Path

from app.config import DATA_DIR, DOWNLOAD_DIR, OUTPUT_DIR


def cleanup_artifacts(download_dir=DOWNLOAD_DIR, output_dir=OUTPUT_DIR):
    removed_any = False

    for path in (download_dir, output_dir):
        if path.exists():
            shutil.rmtree(path)
            print(f"Removed {path}")
            removed_any = True

    if not removed_any:
        print("No data/downloads or data/output_pdfs directory to remove.")


def clear_directory(directory: Path, dry_run: bool = False) -> int:
    """删除目录下的所有文件和子目录，保留目录本身。"""
    removed_count = 0
    if not directory.exists():
        print(f"  目录不存在，跳过: {directory}")
        return removed_count

    for item in sorted(directory.iterdir()):
        if dry_run:
            print(f"  [预览] 将删除: {item}")
            removed_count += 1
            continue

        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            print(f"  已删除: {item}")
            removed_count += 1
        except Exception as exc:
            print(f"  [错误] 无法删除 {item}: {exc}", file=sys.stderr)

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
        print(f"[错误] data 目录不存在: {DATA_DIR}", file=sys.stderr)
        return 1

    subdirs = sorted(p for p in DATA_DIR.iterdir() if p.is_dir())
    if not subdirs:
        print(f"data 目录下没有子目录: {DATA_DIR}")
        return 0

    print("将清空以下目录的内容：")
    for subdir in subdirs:
        print(f"  - {subdir}")

    if args.dry_run:
        print("\n[预览模式] 不会真正删除任何文件。\n")
    elif not args.yes:
        try:
            answer = input("\n确认清空？(yes/no): ")
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return 130
        if answer.strip().lower() not in ("yes", "y"):
            print("已取消")
            return 0
        print()

    total = 0
    for subdir in subdirs:
        print(f"清理: {subdir}")
        total += clear_directory(subdir, dry_run=args.dry_run)

    action = "将删除" if args.dry_run else "已删除"
    print(f"\n{action} {total} 个项目")
    return 0
