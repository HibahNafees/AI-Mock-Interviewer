"""Pressure mode (levels 1–5): between-answer pressure that stays respectful.

Higher levels add to the lower ones. Pressure changes how the interviewer behaves
and how long each answer may run, never how answers are scored. The candidate can
lower or stop it at any time. The composure score compares the session's result
with the candidate's normal (no-pressure) interviews.
"""

from ..extensions import db
from ..models import Report, Session

RESPECT = (
    "Pressure must stay professional and respectful: no insults, sarcasm, raised "
    "voice, or remarks about the person. Challenge the answer, never the candidate."
)
LEVEL_NOTES = {
    1: "Be noticeably more skeptical than usual: ask them to back up claims with specifics.",
    2: 'When an answer is vague or drifts, push back briefly before your question, e.g. "That\'s not quite what I asked." or "Can you be more specific?"',
    3: "Keep your turns short and brisk; don't reassure.",
    4: "Now and then (not every turn) use a curveball follow-up: an unexpected but fair angle on the same topic, e.g. what they'd do if a key assumption were wrong.",
    5: "Be demanding: challenge weak reasoning directly and expect precise, quantified answers.",
}
TIME_LIMITS = {3: 60, 4: 45, 5: 30}
LABELS = {
    0: "Off",
    1: "Skeptical",
    2: "Pushback",
    3: "60 s answers",
    4: "45 s + curveballs",
    5: "30 s, demanding",
}


def notes(level: int) -> list[str]:
    if not level:
        return []
    return [LEVEL_NOTES[n] for n in range(1, level + 1)] + [RESPECT]


def time_limit(level: int | None) -> int | None:
    return TIME_LIMITS.get(level or 0)


def time_line(level: int | None) -> str:
    limit = time_limit(level)
    return f"You have {limit} seconds for this one." if limit else ""


def info(session: Session) -> dict | None:
    if session.mode != "pressure":
        return None
    level = session.pressure_level or 0
    return {
        "level": level,
        "start_level": (session.plan_json or {}).get("pressure_start", level),
        "label": LABELS[level],
        "time_limit_sec": time_limit(level),
    }


def lower(session: Session, level: int) -> None:
    """The candidate can only ease the pressure, never raise it mid-interview."""
    current = session.pressure_level or 0
    if level < current:
        session.pressure_level = level
        db.session.commit()


def composure(session: Session, report: Report) -> dict | None:
    """How well answer quality held up compared with normal interviews."""
    if session.mode != "pressure" or report.overall_score is None:
        return None
    rows = db.session.execute(
        db.select(Report.overall_score, Session.jd_id)
        .join(Session, Report.session_id == Session.id)
        .where(
            Session.user_id == session.user_id,
            Session.id != session.id,
            Session.mode != "pressure",
            Report.overall_score.is_not(None),
        )
    ).all()
    same_job = [s for s, jd in rows if jd == session.jd_id]
    baseline_scores = same_job or [s for s, _ in rows]
    if not baseline_scores:
        return {
            "pct": None,
            "baseline": None,
            "label": "Do a normal interview too, so we can compare how you hold up.",
        }
    baseline = sum(baseline_scores) / len(baseline_scores)
    pct = round(100 * report.overall_score / baseline)
    label = (
        "Held up well under pressure"
        if pct >= 95
        else (
            "A small dip under pressure"
            if pct >= 80
            else "Pressure noticeably affected your answers"
        )
    )
    return {
        "pct": pct,
        "baseline": round(baseline, 2),
        "same_job": bool(same_job),
        "label": label,
    }
