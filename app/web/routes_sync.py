from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import SyncRun
from app.services.notion_sync import sync_notion_reimbursements
from app.web.templates import templates

router = APIRouter(prefix="/sync")


@router.get("")
def sync_page(request: Request, db: Session = Depends(get_db)):
    runs = db.scalars(select(SyncRun).order_by(desc(SyncRun.started_at)).limit(50)).all()
    return templates.TemplateResponse(request, "sync_runs.html", {"runs": runs})


@router.post("/run")
def run_sync():
    sync_notion_reimbursements(mode="manual")
    return RedirectResponse("/sync", status_code=303)
