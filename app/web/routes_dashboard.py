from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.dashboard import get_dashboard_summary
from app.web.templates import templates

router = APIRouter()


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    summary = get_dashboard_summary(db)
    return templates.TemplateResponse(request, "dashboard.html", {"summary": summary})
