import asyncio
import logging
import time
from pathlib import Path

import httpx
from PIL import Image
from pypdf import PdfReader

from app.pdf_service import is_pdf_file

logger = logging.getLogger(__name__)

SAFE_FILENAME_CHARS = {" ", ".", "_", "-"}
_HTTP_RETRIES = 3
_HTTP_BACKOFF = 1.0
_MAX_CONCURRENT = 5  # max parallel downloads

# Shared timeout used by both sync and async paths.
_DEFAULT_TIMEOUT = httpx.Timeout(10.0, read=30.0)


# ── async download core ───────────────────────────────────────────────────


async def _download_with_retry_async(
    url: str,
    client: httpx.AsyncClient,
) -> bytes:
    """Async download with exponential backoff retries."""
    last_exc = None
    for attempt in range(_HTTP_RETRIES):
        try:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                wait = _HTTP_BACKOFF * (2 ** attempt)
                logger.warning("Rate limited (429), retrying in %.1fs...", wait)
                await asyncio.sleep(wait)
                continue
            logger.error("HTTP error downloading %s: %s", url[:80], exc)
            raise
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < _HTTP_RETRIES - 1:
                wait = _HTTP_BACKOFF * (2 ** attempt)
                logger.warning("Network error for %s, retrying in %.1fs...", url[:80], wait)
                await asyncio.sleep(wait)
                continue
            logger.error("Download failed after %d retries: %s", _HTTP_RETRIES, exc)
            raise last_exc
    raise last_exc  # type: ignore[misc]


async def _download_one(
    index: int,
    item: dict,
    download_dir: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    """Download a single media item and return its metadata, or None on failure."""
    url = item["url"]
    item_id = item.get("id") or f"file_{index}"

    try:
        filename = url.split("?")[0].split("/")[-1] or item_id
        local_path = resolve_download_path(download_dir, item_id, filename)

        logger.info("Downloading %s... to %s", url[:50], local_path)

        async with semaphore:
            start_time = time.time()
            content = await _download_with_retry_async(url, client)
            elapsed = time.time() - start_time

        local_path.write_bytes(content)

        logger.info(
            "Downloaded %s (%.1f KB) in %.1fs",
            local_path.name,
            len(content) / 1024,
            elapsed,
        )

        file_type = _classify_file(local_path)
        if file_type is None:
            logger.warning("Skipping unknown file type: %s", local_path)
            local_path.unlink(missing_ok=True)
            return None

        return {"path": local_path, "type": file_type}
    except Exception as exc:
        logger.error("Failed to download %s: %s", url, exc)
        return None


async def download_media_async(
    media_items: list[dict],
    download_dir: str,
    max_concurrent: int = _MAX_CONCURRENT,
) -> list[dict]:
    """Download media items concurrently with bounded parallelism.

    Returns a list of ``{"path": Path, "type": str}`` dicts.
    """
    if not media_items:
        return []

    semaphore = asyncio.Semaphore(max(max_concurrent, 1))
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        tasks = [
            _download_one(i, item, download_dir, client, semaphore)
            for i, item in enumerate(media_items, start=1)
        ]
        results = await asyncio.gather(*tasks)

    return [r for r in results if r is not None]


# ── synchronous facade (public API) ───────────────────────────────────────


def download_media(media_items: list[dict], download_dir: str) -> list[dict]:
    """Download media items concurrently (sync wrapper).

    For callers already inside an event loop, use :func:`download_media_async`
    directly to avoid nesting issues.
    """
    if not media_items:
        return []
    return asyncio.run(download_media_async(media_items, download_dir))


# ── file utilities ────────────────────────────────────────────────────────


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


def _classify_file(file_path):
    """Return the file type ('image', 'pdf', or None)."""
    if is_image_file(file_path):
        return "image"
    if is_pdf_file(file_path):
        return "pdf"
    try:
        PdfReader(file_path)
        return "pdf"
    except Exception:
        return None
