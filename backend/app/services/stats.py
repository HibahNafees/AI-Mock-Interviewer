"""Progress numbers for the dashboard. Computed from saved rows; no Fire calls."""

from collections import defaultdict
from datetime import date, timedelta

from ..extensions import db
from ..models import Answer, Evaluation, Question, Report, Session
from .limits import today

INTERVIEWS_PER_LEVEL = 2
MAX_LEVEL = 10


def _streak(days: set[date]) -> int:
    """Consecutive practice days ending today (or yesterday, if not yet today)."""
    day = today()
    if day not in days:
        day -= timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def user_stats(user_id: int) -> dict:
    sessions = db.session.scalars(
        db.select(Session).filter_by(user_id=user_id).order_by(Session.created_at)
    ).all()
    ids = [s.id for s in sessions]
    started = [s for s in sessions if s.started_at]
    completed = [s for s in sessions if s.status == "completed"]
    reports = {
        r.session_id: r
        for r in db.session.scalars(
            db.select(Report).where(
                Report.session_id.in_(ids), Report.overall_score.is_not(None)
            )
        )
    }
    answers = db.session.execute(
        db.select(Answer, Question)
        .join(Question, Answer.question_id == Question.id)
        .where(
            Question.session_id.in_(ids),
            Question.is_icebreaker.is_(False),
            Question.is_candidate_qa.is_(False),
        )
    ).all()

    history = [
        {
            "session_id": s.id,
            "date": (s.started_at or s.created_at).date().isoformat(),
            "score": reports[s.id].overall_score,
            "role": (s.plan_json or {}).get("role_title") or "Interview",
        }
        for s in sessions
        if s.id in reports
    ]
    scores = [h["score"] for h in history]

    roles: dict[str, dict] = {}
    for s in completed:
        role = (s.plan_json or {}).get("role_title") or "Interview"
        r = roles.setdefault(role, {"role": role, "interviews": 0, "scores": []})
        r["interviews"] += 1
        if s.id in reports:
            r["scores"].append(reports[s.id].overall_score)

    # Skills: every criterion the user was scored on, averaged across first attempts.
    first_ids = [a.id for a, _ in answers if a.attempt_no == 1]
    skill_scores: dict[str, list[int]] = defaultdict(list)
    names: dict[str, str] = {}
    if first_ids:
        for e in db.session.scalars(
            db.select(Evaluation).where(Evaluation.answer_id.in_(first_ids))
        ):
            for c in (e.rubric_scores_json or {}).get("criteria", []):
                if c.get("score") is None:
                    continue
                key = c["name"].strip().lower()
                names.setdefault(key, c["name"].strip())
                skill_scores[key].append(c["score"])
    skills = sorted(
        (
            {"name": names[k], "score": _avg(v), "count": len(v)}
            for k, v in skill_scores.items()
        ),
        key=lambda s: (-s["count"], s["name"]),
    )[:6]

    level = min(MAX_LEVEL, 1 + len(completed) // INTERVIEWS_PER_LEVEL)
    return {
        "interviews": len(completed),
        "started": len(started),
        "practice_minutes": round(
            sum((a.duration_ms or 0) for a, _ in answers) / 60000
        ),
        "questions_answered": sum(1 for a, q in answers if a.attempt_no == 1),
        "retries": sum(1 for a, _ in answers if a.attempt_no > 1),
        "average_score": _avg(scores),
        "best_score": max(scores) if scores else None,
        "latest_score": scores[-1] if scores else None,
        "improvement": round(scores[-1] - scores[0], 2) if len(scores) > 1 else None,
        "history": history[-12:],
        "roles": sorted(
            (
                {
                    "role": r["role"],
                    "interviews": r["interviews"],
                    "average_score": _avg(r["scores"]),
                }
                for r in roles.values()
            ),
            key=lambda r: (-r["interviews"], r["role"]),
        ),
        "skills": skills,
        "streak_days": _streak(
            {(s.started_at or s.created_at).date() for s in started}
        ),
        "level": level,
        "next_level_in": (
            None
            if level == MAX_LEVEL
            else INTERVIEWS_PER_LEVEL - len(completed) % INTERVIEWS_PER_LEVEL
        ),
    }
