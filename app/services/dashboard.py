from datetime import date, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.models import ReimbursementRecord, ReimbursementStatusEvent, SyncRun


def get_dashboard_summary(session: Session):
    total_records = session.scalar(
        select(func.count()).select_from(ReimbursementRecord).where(
            ReimbursementRecord.is_archived.is_(False)
        )
    ) or 0
    total_amount = session.scalar(
        select(func.coalesce(func.sum(ReimbursementRecord.amount), 0)).where(
            ReimbursementRecord.is_archived.is_(False)
        )
    ) or 0
    recent_sync = session.scalar(select(SyncRun).order_by(desc(SyncRun.started_at)).limit(1))
    recent_events = session.scalar(
        select(func.count()).select_from(ReimbursementStatusEvent).where(
            ReimbursementStatusEvent.changed_date >= date.today() - timedelta(days=7)
        )
    ) or 0
    status_rows = session.execute(
        select(
            ReimbursementRecord.status,
            func.count(ReimbursementRecord.id),
            func.coalesce(func.sum(ReimbursementRecord.amount), 0),
        )
        .where(ReimbursementRecord.is_archived.is_(False))
        .group_by(ReimbursementRecord.status)
        .order_by(ReimbursementRecord.status)
    ).all()
    return {
        "total_records": total_records,
        "total_amount": float(total_amount),
        "recent_sync": recent_sync,
        "recent_events": recent_events,
        "status_rows": status_rows,
    }

