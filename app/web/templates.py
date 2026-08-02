from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _status_class_filter(status_name: str | None) -> str:
    """Return a CSS class name based on the status number prefix."""
    if not status_name:
        return "status-default"
    # Extract the number before the first dash
    if "-" in status_name:
        try:
            num = int(status_name.split("-")[0])
            return f"status-{num}"
        except ValueError:
            pass
    return "status-default"


def _beijing_time_filter(dt: datetime | None) -> str:
    """Convert UTC datetime to Beijing Time (UTC+8) and format."""
    if dt is None:
        return ""
    beijing_tz = timezone(timedelta(hours=8))
    if dt.tzinfo is None:
        # Naive datetime is treated as UTC
        dt = dt.replace(tzinfo=timezone.utc)
    beijing_dt = dt.astimezone(beijing_tz)
    return beijing_dt.strftime("%Y-%m-%d %H:%M:%S")


templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
templates.env.filters["status_class"] = _status_class_filter
templates.env.filters["beijing_time"] = _beijing_time_filter

