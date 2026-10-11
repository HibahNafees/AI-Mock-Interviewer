"""Privacy controls: expired documents, "Delete my data", and report share links."""

import secrets

from sqlalchemy import delete, select

from ..extensions import db
from ..models import AnonSpend, Document, Report, UsageLimit, User
from ..models.base import utcnow


def purge_expired_documents() -> int:
    """Delete résumés and job descriptions past their 30 days (unless saved).

    Their analyses go with them (ON DELETE CASCADE); sessions keep their plan
    and lose only the link to the document.
    """
    result = db.session.execute(
        delete(Document).where(
            Document.expires_at.is_not(None), Document.expires_at <= utcnow()
        )
    )
    db.session.commit()
    return result.rowcount or 0


def delete_user(user_id: int) -> None:
    """Delete the account and everything in it in one go.

    The Fire spend it used stays in the monthly total (moved to the
    not-tied-to-a-user rows), so deleting an account can't reset the budget.
    """
    for row in db.session.scalars(select(UsageLimit).filter_by(user_id=user_id)):
        spend = float(row.fire_spend_usd or 0)
        if not spend and not row.llm_calls:
            continue
        anon = db.session.get(AnonSpend, row.date)
        if anon is None:
            anon = AnonSpend(date=row.date, llm_calls=0, fire_spend_usd=0)
            db.session.add(anon)
        anon.llm_calls = (anon.llm_calls or 0) + (row.llm_calls or 0)
        anon.fire_spend_usd = float(anon.fire_spend_usd or 0) + spend
    db.session.flush()
    # Every user table cascades from users.id (decodes are kept, unowned:
    # they hold only a hash of the job description and its interpretation).
    db.session.execute(delete(User).where(User.id == user_id))
    db.session.commit()


def share_report(report: Report) -> str:
    if not report.share_token:
        report.share_token = secrets.token_urlsafe(24)
        db.session.commit()
    return report.share_token


def revoke_share(report: Report) -> None:
    report.share_token = None
    db.session.commit()


def shared_report(token: str) -> Report | None:
    if not token:
        return None
    return db.session.scalar(select(Report).filter_by(share_token=token))
