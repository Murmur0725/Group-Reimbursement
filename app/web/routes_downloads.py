from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import DATA_DIR

router = APIRouter(prefix="/downloads")

ALLOWED_DOWNLOAD_DIRS = {
    "downloads": DATA_DIR / "downloads",
    "output_pdfs": DATA_DIR / "output_pdfs",
    "fapiao": DATA_DIR / "fapiao",
}


@router.get("/{bucket}/{file_path:path}")
def download_file(bucket: str, file_path: str):
    base_dir = ALLOWED_DOWNLOAD_DIRS.get(bucket)
    if base_dir is None:
        raise HTTPException(status_code=404, detail="Unknown download bucket")

    requested = (base_dir / file_path).resolve()
    allowed_root = base_dir.resolve()
    try:
        requested.relative_to(allowed_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid file path") from exc

    if not requested.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=Path(requested),
        filename=requested.name,
        media_type="application/octet-stream",
    )
