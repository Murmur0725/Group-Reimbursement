from pathlib import Path

import requests
from PIL import Image
from pypdf import PdfReader

from app.pdf_service import is_pdf_file

SAFE_FILENAME_CHARS = {" ", ".", "_", "-"}


def sanitize_filename(value, fallback="file"):
    sanitized = "".join(
        char for char in str(value) if char.isalnum() or char in SAFE_FILENAME_CHARS
    ).strip()
    return sanitized or fallback


def resolve_download_path(download_dir, item_id, filename):
    directory = Path(download_dir)
    directory.mkdir(parents=True, exist_ok=True)

    safe_item_id = sanitize_filename(item_id, "file")
    safe_filename = sanitize_filename(filename, safe_item_id)
    candidate = directory / f"{safe_item_id}_{safe_filename}"

    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2

    while True:
        next_candidate = directory / f"{stem}_{counter}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        counter += 1


def is_image_file(file_path):
    try:
        image = Image.open(file_path)
        image.verify()
        return True
    except Exception:
        return False


def download_media(media_items, download_dir):
    downloaded_files = []

    for index, item in enumerate(media_items, start=1):
        url = item["url"]
        item_id = item.get("id") or f"file_{index}"

        try:
            filename = url.split("?")[0].split("/")[-1] or item_id
            local_path = resolve_download_path(download_dir, item_id, filename)

            print(f"Downloading {url[:50]}... to {local_path}")

            response = requests.get(url, stream=True, timeout=30.0)
            response.raise_for_status()

            with local_path.open("wb") as file_obj:
                for chunk in response.iter_content(chunk_size=8192):
                    file_obj.write(chunk)

            if is_image_file(local_path):
                file_type = "image"
            elif is_pdf_file(local_path):
                file_type = "pdf"
            else:
                try:
                    PdfReader(local_path)
                    file_type = "pdf"
                except Exception:
                    print(f"Skipping unknown file type: {local_path}")
                    local_path.unlink(missing_ok=True)
                    continue

            downloaded_files.append({
                "path": local_path,
                "type": file_type,
            })
        except Exception as exc:
            print(f"Failed to download {url}: {exc}")

    return downloaded_files
