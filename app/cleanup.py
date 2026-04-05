import shutil

from app.config import DOWNLOAD_DIR, OUTPUT_DIR


def cleanup_artifacts(download_dir=DOWNLOAD_DIR, output_dir=OUTPUT_DIR):
    removed_any = False

    for path in (download_dir, output_dir):
        if path.exists():
            shutil.rmtree(path)
            print(f"Removed {path}")
            removed_any = True

    if not removed_any:
        print("No data/downloads or data/output_pdfs directory to remove.")
