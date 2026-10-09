"""Usage caps and Fire spend tracking (usage_limits)."""

from datetime import date, datetime, timezone

from flask import current_app
from sqlalchemy import func

from ..extensions import db
from ..models import Session, UsageLimit

LONG_SESSION_MIN = 60


class LimitReached(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def today() -> date:
    return datetime.now(timezone.utc).date()


def _row(user_id: int) -> UsageLimit:
    row = db.session.get(UsageLimit, (user_id, today()))
    if row is None:
        row = UsageLimit(
            user_id=user_id,
            date=today(),
            minutes_used=0,
            llm_calls=0,
            sessions_count=0,
            decoder_runs=0,
            fire_spend_usd=0,
        )
        db.session.add(row)
    return row


def record_fire_call(user_id: int, price_usd: float) -> None:
    """Add one Fire call's charged price to today's row for this user."""
    row = _row(user_id)
    row.llm_calls += 1
    row.fire_spend_usd = (row.fire_spend_usd or 0) + price_usd
    db.session.commit()


def month_spend_usd() -> float:
    """Total Fire spend across all users this calendar month."""
    start = today().replace(day=1)
    total = db.session.scalar(
        db.select(func.coalesce(func.sum(UsageLimit.fire_spend_usd), 0)).where(
            UsageLimit.date >= start
        )
    )
    return float(total or 0)


def check_budget() -> None:
    """New Fire work pauses once the monthly budget is used up."""
    if month_spend_usd() >= current_app.config["FIRE_MONTHLY_BUDGET_USD"]:
        raise LimitReached(
            "This month's AI budget is used up, so new interviews are paused "
            "until next month."
        )


def check_can_start(user_id: int, duration_min: int) -> None:
    """Daily caps for a new session (checked before it starts)."""
    check_budget()
    cfg = current_app.config
    row = db.session.get(UsageLimit, (user_id, today()))
    used = row.minutes_used if row else 0
    if used + duration_min > cfg["DAILY_INTERVIEW_MINUTES"]:
        left = max(0, cfg["DAILY_INTERVIEW_MINUTES"] - int(used))
        raise LimitReached(
            f"That would go over today's {cfg['DAILY_INTERVIEW_MINUTES']} interview "
            f"minutes ({left} left). Try a shorter interview or come back tomorrow."
        )
    if duration_min >= LONG_SESSION_MIN:
        start = datetime.combine(today(), datetime.min.time())
        long_today = db.session.scalar(
            db.select(func.count(Session.id)).where(
                Session.user_id == user_id,
                Session.duration_min >= LONG_SESSION_MIN,
                Session.started_at >= start,
            )
        )
        if long_today >= cfg["DAILY_LONG_SESSIONS"]:
            raise LimitReached(
                "You've already done a 60-minute interview today; try a shorter one."
            )


def check_can_plan(user_id: int) -> None:
    """Each plan costs Fire calls, so cap how many a user can generate per day."""
    start = datetime.combine(today(), datetime.min.time())
    made = db.session.scalar(
        db.select(func.count(Session.id)).where(
            Session.user_id == user_id, Session.created_at >= start
        )
    )
    cap = current_app.config["DAILY_PLANS"]
    if made >= cap:
        raise LimitReached(
            f"You've generated {cap} interview plans today; try again tomorrow."
        )


def record_session_start(user_id: int, duration_min: int) -> None:
    row = _row(user_id)
    row.sessions_count += 1
    row.minutes_used += duration_min
    db.session.commit()
