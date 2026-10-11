"""Admin usage view: daily usage and estimated Fire spend against the budget."""

from datetime import timedelta

from flask import current_app
from sqlalchemy import func, select

from ..extensions import db
from ..models import AnonSpend, UsageLimit, User
from .limits import month_spend_usd, today

DAYS = 30
TOP_USERS = 10


def is_admin(user: User | None) -> bool:
    return bool(user) and user.email.lower() in current_app.config["ADMIN_EMAILS"]


def usage() -> dict:
    """The last 30 days per day, this month's top spenders, and the budget."""
    start = today() - timedelta(days=DAYS - 1)
    days = {
        start
        + timedelta(days=i): {
            "users": 0,
            "minutes": 0.0,
            "sessions": 0,
            "fire_calls": 0,
            "spend_usd": 0.0,
            "decoder_runs": 0,
        }
        for i in range(DAYS)
    }
    rows = db.session.execute(
        select(
            UsageLimit.date,
            func.count(UsageLimit.user_id),
            func.sum(UsageLimit.minutes_used),
            func.sum(UsageLimit.sessions_count),
            func.sum(UsageLimit.llm_calls),
            func.sum(UsageLimit.fire_spend_usd),
            func.sum(UsageLimit.decoder_runs),
        )
        .where(UsageLimit.date >= start)
        .group_by(UsageLimit.date)
    )
    for d, users, minutes, sessions, calls, spend, decodes in rows:
        days[d].update(
            users=users,
            minutes=round(float(minutes or 0), 1),
            sessions=int(sessions or 0),
            fire_calls=int(calls or 0),
            spend_usd=float(spend or 0),
            decoder_runs=int(decodes or 0),
        )
    for a in db.session.scalars(select(AnonSpend).where(AnonSpend.date >= start)):
        days[a.date]["fire_calls"] += a.llm_calls or 0
        days[a.date]["spend_usd"] += float(a.fire_spend_usd or 0)

    month_start = today().replace(day=1)
    top = db.session.execute(
        select(
            User.email,
            func.sum(UsageLimit.fire_spend_usd).label("spend"),
            func.sum(UsageLimit.minutes_used),
            func.sum(UsageLimit.sessions_count),
        )
        .join(User, User.id == UsageLimit.user_id)
        .where(UsageLimit.date >= month_start)
        .group_by(User.email)
        .order_by(func.sum(UsageLimit.fire_spend_usd).desc())
        .limit(TOP_USERS)
    )
    budget = float(current_app.config["FIRE_MONTHLY_BUDGET_USD"])
    spent = month_spend_usd()
    return {
        "budget_usd": budget,
        "month_spend_usd": round(spent, 6),
        "budget_left_usd": round(max(budget - spent, 0), 6),
        "paused": spent >= budget,
        "users_total": db.session.scalar(select(func.count(User.id))),
        "days": [
            {"date": d.isoformat(), **v, "spend_usd": round(v["spend_usd"], 6)}
            for d, v in sorted(days.items(), reverse=True)
        ],
        "top_users": [
            {
                "email": email,
                "spend_usd": round(float(spend or 0), 6),
                "minutes": round(float(minutes or 0), 1),
                "sessions": int(sessions or 0),
            }
            for email, spend, minutes, sessions in top
        ],
    }
