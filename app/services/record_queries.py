from sqlalchemy import Integer, cast, desc, func, select
from sqlalchemy.orm import Session

from app.db.models import ReimbursementRecord


def build_records_query(
    status: str | None = None,
    applicant: str | None = None,
    reimbursed_to: str | None = None,
    q: str | None = None,
    amount: float | None = None,
    tolerance: float = 0,
):
    query = select(ReimbursementRecord).where(ReimbursementRecord.is_archived.is_(False))
    if status:
        query = query.where(ReimbursementRecord.status == status)
    if applicant:
        query = query.where(ReimbursementRecord.applicant == applicant)
    if reimbursed_to:
        query = query.where(ReimbursementRecord.reimbursed_to == reimbursed_to)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            ReimbursementRecord.title.like(pattern)
            | ReimbursementRecord.number.like(pattern)
        )

    status_number = cast(
        func.substr(
            ReimbursementRecord.status,
            1,
            func.instr(ReimbursementRecord.status, "-") - 1,
        ),
        Integer,
    )
    if amount is not None:
        difference = func.abs(ReimbursementRecord.amount - amount)
        query = query.where(
            ReimbursementRecord.amount.is_not(None),
            ReimbursementRecord.amount >= amount - tolerance,
            ReimbursementRecord.amount <= amount + tolerance,
        )
        return query.order_by(
            difference.asc(),
            desc(status_number),
            desc(ReimbursementRecord.last_synced_at),
        )

    return query.order_by(desc(status_number), desc(ReimbursementRecord.last_synced_at))


def get_filtered_records(
    session: Session,
    status: str | None = None,
    applicant: str | None = None,
    reimbursed_to: str | None = None,
    q: str | None = None,
    amount: float | None = None,
    tolerance: float = 0,
):
    return session.scalars(
        build_records_query(
            status=status,
            applicant=applicant,
            reimbursed_to=reimbursed_to,
            q=q,
            amount=amount,
            tolerance=tolerance,
        )
    ).all()


def search_by_amount(session: Session, amount: float, tolerance: float = 0):
    """Amount search ordered by absolute distance to the target amount."""
    return get_filtered_records(session, amount=amount, tolerance=tolerance)

