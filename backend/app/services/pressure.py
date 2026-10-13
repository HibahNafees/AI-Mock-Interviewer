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
    1: 'Be noticeably more skeptical than usual: after most answers, question one claim and ask them to back it up ("How do you know it was your change that fixed it?").',
    2: 'When an answer is vague, drifts or says "we", push back before your question ("That\'s not quite what I asked.", "What did you do, specifically?"). While follow_up is in the list, prefer a challenging follow-up to moving on, even after a good answer. When you move on after a vague answer, first say in a few words what was missing ("That didn\'t answer it. Moving on."), then ask the next question.',
    3: "Keep your turns short and brisk, under 30 words; don't reassure.",
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


# Questions the plan adds for a pressure interview (T-96: pressure only changed
# the interviewer's tone, so the questions themselves felt the same).
PLAN_NOTES = {
    1: "Make about a third of the questions pressure questions that test composure: challenge a specific claim from the résumé (\"Your résumé says you led X. What exactly was your part?\"), ask about a failure or a real weakness and what they'd do differently, or why they're a better fit than someone with more experience.",
    3: "Make about half of them pressure questions, and give some tight constraints (little time, little budget, a deliberately ambiguous brief).",
    5: "Make most of them pressure questions, including at least one that challenges a gap or weak spot in the résumé.",
}


def plan_rule(level: int | None) -> str:
    """The plan prompt's pressure line, "" for a normal interview."""
    if not level:
        return ""
    notes = [n for lv, n in PLAN_NOTES.items() if lv <= level]
    return (
        f"This is a pressure interview, level {level} of 5. "
        + " ".join(notes)
        + " Keep every question fair, job-related and respectful."
        + NO_PRESSURE_NOTE
    )


# Coding and system design questions stay pressure-free: no time limit, no
# pushback, no tight constraints (T-134: "write code in 45 seconds").
NO_PRESSURE_MODULES = ("coding", "system_design")
NO_PRESSURE_NOTE = (
    " Pressure is for the other sections only: coding problems and system design "
    "questions stay normal, with no tight time limits or extra constraints."
)


def exempt(session: Session, section: str | None) -> bool:
    """A coding or system design section: never under pressure."""
    for s in (session.plan_json or {}).get("sections", []):
        if s.get("name") == section:
            return s.get("module") in NO_PRESSURE_MODULES
    return False


def applies(session: Session, section: str | None) -> bool:
    """Whether pressure applies to a question in this section right now."""
    return bool(session.pressure_level) and not exempt(session, section)


def time_limit(level: int | None) -> int | None:
    return TIME_LIMITS.get(level or 0)


def time_line(level: int | None) -> str:
    limit = time_limit(level)
    return f"You have {limit} seconds for this one." if limit else ""


def is_on(session: Session) -> bool:
    """A pressure interview, one-to-one (mode "pressure") or a panel with pressure
    (T-132: the mode is "panel", so the level started at creation says it)."""
    return session.mode == "pressure" or "pressure_start" in (session.plan_json or {})


def timed(session: Session) -> bool:
    """Whether answers had a time limit at any point (it can only be eased)."""
    if not is_on(session):
        return False
    start = (session.plan_json or {}).get("pressure_start", session.pressure_level)
    return time_limit(start) is not None


def info(session: Session) -> dict | None:
    if not is_on(session):
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
    if not is_on(session) or report.overall_score is None:
        return None
    rows = db.session.execute(
        db.select(Report.overall_score, Session.jd_id)
        .join(Session, Report.session_id == Session.id)
        .where(
            Session.user_id == session.user_id,
            Session.id != session.id,
            Session.mode != "pressure",
            Session.pressure_level.is_(None),  # a panel with pressure isn't a baseline
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
