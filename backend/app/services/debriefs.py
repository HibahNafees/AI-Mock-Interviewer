"""Post-interview debrief: recall-only, never recordings.

The user types (or speaks; the clip is transcribed and discarded) the questions and
answers they remember from a real interview. That becomes a completed "debrief"
session, scored by the normal report pipeline; one extra Fire call predicts the
next round, which can be practiced as a new interview.
"""

import logging
import re

from pydantic import BaseModel, Field

from .. import modules
from ..extensions import db
from ..models import Answer, Debrief, Document, Question, Session
from ..models.base import utcnow
from . import planning
from .llm import chat_json, render
from .planning import PlanOut, PlanSectionOut, save_plan
from .scoring import SYSTEM

log = logging.getLogger(__name__)

SECTION = "Recalled interview"
# Used when no job description is chosen (no Fire call for a rubric).
DEFAULT_RUBRIC = {
    "criteria": [
        {
            "name": "Relevance",
            "kind": "universal",
            "weight": 0.2,
            "description": "Answers the question that was asked.",
            "strong_answer": "Addresses the question directly, without drifting.",
        },
        {
            "name": "Specificity",
            "kind": "role",
            "weight": 0.2,
            "description": "Concrete examples, numbers and details.",
            "strong_answer": "A specific example with real details.",
        },
        {
            "name": "Ownership",
            "kind": "role",
            "weight": 0.2,
            "description": "Makes their own contribution clear.",
            "strong_answer": "Says what they personally did and decided.",
        },
        {
            "name": "Impact",
            "kind": "role",
            "weight": 0.15,
            "description": "Shows the result or what changed.",
            "strong_answer": "Ends with a measured or clearly stated outcome.",
        },
        {
            "name": "Structure",
            "kind": "universal",
            "weight": 0.15,
            "description": "Logical, easy-to-follow order.",
            "strong_answer": "Leads with the point, then specifics, then the result.",
        },
        {
            "name": "Clarity",
            "kind": "universal",
            "weight": 0.1,
            "description": "Clear, concise wording.",
            "strong_answer": "Easy to follow on first hearing.",
        },
    ]
}
NEXT_ROUND = "Next round"
ALLOWED_MODULES = {"behavioral", "resume_deepdive", "technical", "case", "scenario"}


class Prediction(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    why: str = Field(default="", max_length=300)
    module: str = "behavioral"


class PredictionsOut(BaseModel):
    questions: list[Prediction] = Field(min_length=1, max_length=8)


# "Do you have any questions for us?" and the like.
THEIR_QUESTIONS_RE = re.compile(
    r"\bquestions?\b[^.?!]*\bfor (?:us|me|the team|our team|them)\b"
    r"|\banything (?:you'?d like|you want|else) to ask\b"
    r"|\bwhat (?:would you like|do you want) to (?:ask|know)\b",
    re.IGNORECASE,
)


def create(
    user_id: int,
    role: str,
    company: str | None,
    round_: str | None,
    items: list[dict],
    resume: Document | None,
    jd: Document | None,
) -> Debrief:
    """Save the recalled interview as a completed session (scored by the report)."""
    analysis = planning.analyze_jd(user_id, jd) if jd else None
    rubric = (
        planning.build_rubric(user_id, analysis, "mid").model_dump()
        if analysis
        else DEFAULT_RUBRIC
    )
    now = utcnow()
    minutes = max(5, min(60, 3 * len(items)))
    session = Session(
        user_id=user_id,
        resume_id=resume.id if resume else None,
        jd_id=jd.id if jd else None,
        mode="debrief",
        duration_min=minutes,
        difficulty="mid",
        persona="neutral",
        status="completed",
        started_at=now,
        ended_at=now,
        rubric_json=rubric,
        plan_json={
            "role_title": role,
            "analysis": (
                planning.analysis_summary(analysis)
                if analysis
                else {"role_title": role}
            ),
            "focus": "mixed",
            "debrief": {"company": company, "round": round_},
            "sections": [
                {
                    "name": SECTION,
                    "module": "behavioral",
                    "minutes": minutes,
                    "scenario": None,
                }
            ],
        },
    )
    db.session.add(session)
    db.session.flush()
    budget = round(minutes * 60 / len(items))
    for n, item in enumerate(items, start=1):
        q = Question(
            session_id=session.id,
            section=SECTION,
            order_no=n,
            # Their questions at the end are rated as questions, not scored as an
            # answer (T-105: the scorer had nothing to grade or rewrite).
            is_candidate_qa=bool(THEIR_QUESTIONS_RE.search(item["question"])),
            text=item["question"],
            budget_sec=budget,
            is_bonus=False,
            asked_at=now,
            asked_text=item["question"],
        )
        db.session.add(q)
        db.session.flush()
        db.session.add(
            Answer(
                question_id=q.id,
                transcript=item["answer"],
                duration_ms=item.get("duration_ms"),
                attempt_no=1,
                input_mode=item.get("input_mode") or "text",
            )
        )
    debrief = Debrief(
        user_id=user_id,
        company=company,
        role=role,
        round=round_,
        recalled_qa_json=items,
        session_id=session.id,
    )
    db.session.add(debrief)
    db.session.commit()
    return debrief


def predict(user_id: int, debrief: Debrief, items: list, done: dict) -> None:
    """Likely next-round questions (one Fire call, once per debrief)."""
    if (debrief.analysis_json or {}).get("next_round"):
        return
    session = db.session.get(Session, debrief.session_id)
    results = []
    for t in items:
        e = done.get(t.main_answer.id)
        if e:
            results.append(
                {
                    "question": t.root.text,
                    "score": e.score,
                    "missing": [
                        m["point"]
                        for m in (e.missing_points_json or [])
                        if not m["covered"]
                    ][:3],
                }
            )
    analysis = (session.plan_json or {}).get("analysis") or {}
    out = chat_json(
        user_id,
        render(
            "next_round",
            role=debrief.role,
            company=f" at {debrief.company}" if debrief.company else "",
            round=f" ({debrief.round})" if debrief.round else "",
            items=debrief.recalled_qa_json,
            results=results,
            competencies=[c.get("name") for c in analysis.get("competencies", [])],
        ),
        PredictionsOut,
        SYSTEM,
        max_tokens=900,
        temperature=0.4,
    )
    debrief.analysis_json = {
        **(debrief.analysis_json or {}),
        "next_round": [
            {
                "question": p.question.strip(),
                "why": p.why.strip(),
                "module": p.module if p.module in ALLOWED_MODULES else "behavioral",
            }
            for p in out.questions
        ][:6],
    }
    db.session.commit()


def practice_next_round(
    user_id: int, debrief: Debrief, duration_min: int
) -> Session | None:
    """A planned mock interview from the predicted next-round questions."""
    predicted = (debrief.analysis_json or {}).get("next_round") or []
    if not predicted:
        return None
    source = db.session.get(Session, debrief.session_id)
    by_module: dict[str, list[str]] = {}
    for p in predicted:
        by_module.setdefault(p["module"], []).append(p["question"])
    names = list(by_module)
    minutes = [duration_min // len(names)] * len(names)
    minutes[0] += duration_min - sum(minutes)
    session = Session(
        user_id=user_id,
        resume_id=source.resume_id,
        jd_id=source.jd_id,
        mode="standard",
        duration_min=duration_min,
        difficulty=source.difficulty,
        persona="neutral",
        status="planned",
        rubric_json=source.rubric_json,
        plan_json={
            "analysis": (source.plan_json or {}).get("analysis"),
            "focus": "mixed",
            "next_round_of": debrief.id,
        },
    )
    db.session.add(session)
    db.session.flush()
    save_plan(
        session,
        PlanOut(
            sections=[
                PlanSectionOut(
                    name=(
                        f"{NEXT_ROUND}: {modules.MODULES[m].label}"
                        if len(names) > 1
                        else NEXT_ROUND
                    ),
                    module=m,
                    minutes=max(1, mins),
                    questions=qs[:4],
                )
                for m, qs, mins in zip(names, by_module.values(), minutes)
            ],
            reserve=[],
        ),
        role_title=debrief.role,
    )
    return session


def _jd_info(d: Debrief) -> dict | None:
    """The job description the debrief was scored against, while it still exists."""
    session = db.session.get(Session, d.session_id) if d.session_id else None
    jd = db.session.get(Document, session.jd_id) if session and session.jd_id else None
    if jd is None or (jd.expires_at and jd.expires_at <= utcnow()):
        return None
    return {"id": jd.id, "title": jd.title, "saved": jd.expires_at is None}


def debrief_dict(d: Debrief) -> dict:
    return {
        "id": d.id,
        "role": d.role,
        "company": d.company,
        "round": d.round,
        "session_id": d.session_id,
        "items": len(d.recalled_qa_json or []),
        "next_round": (d.analysis_json or {}).get("next_round") or [],
        "jd": _jd_info(d),
        "created_at": d.created_at.isoformat() + "Z",
    }
