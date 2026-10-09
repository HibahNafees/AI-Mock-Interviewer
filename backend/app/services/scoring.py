"""Score one question (main answer + follow-ups) and write its stronger version.

One Fire chat call per question covers scores, missing points, weak moments, STAR
and the rewrite. The weighted score is computed here, not by the model.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

from ..extensions import db
from ..models import Document, Evaluation, Session
from .analytics import Clip, delivery
from .llm import chat_json, render

SYSTEM = (
    "You are an expert, fair interview coach. You give honest practice feedback and "
    "never invent facts about the candidate. Reply with a single JSON object only, "
    "no prose and no code fences."
)
MAX_RESUME_CHARS = 6000
VERDICTS = ((4.0, "hire"), (3.0, "lean hire"), (0.0, "no hire"))
SPACE_RE = re.compile(r"\s+")


class CriterionScore(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    score: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=400)


class WeakMoment(BaseModel):
    quote: str = Field(min_length=1, max_length=400)
    why: str = Field(min_length=1, max_length=300)


class MissingPoint(BaseModel):
    point: str = Field(min_length=1, max_length=300)
    covered: bool


class Star(BaseModel):
    situation: bool
    task: bool
    action: bool
    result: bool
    note: str = Field(default="", max_length=300)


class Change(BaseModel):
    kind: Literal["added", "cut", "reframed"]
    text: str = Field(min_length=1, max_length=400)
    reason: str = Field(default="", max_length=300)


class ScoreOut(BaseModel):
    criteria: list[CriterionScore] = Field(min_length=1, max_length=12)
    summary: str = Field(min_length=1, max_length=600)
    weak_moments: list[WeakMoment] = Field(default_factory=list, max_length=5)
    missing_points: list[MissingPoint] = Field(default_factory=list, max_length=8)
    star: Star | None = None
    stronger_version: str = Field(min_length=1, max_length=4000)
    changes: list[Change] = Field(default_factory=list, max_length=8)
    tips: list[str] = Field(default_factory=list, max_length=3)


def _norm(text: str) -> str:
    return SPACE_RE.sub(" ", text).strip().lower()


def weighted_score(
    scores: list[CriterionScore], rubric: dict | None
) -> tuple[float, list[dict]]:
    """Weighted 1–5 score over the rubric criteria the model scored."""
    by_name = {_norm(s.name): s for s in scores}
    rows = []
    for c in (rubric or {}).get("criteria", []):
        s = by_name.get(_norm(c["name"]))
        if s is not None:
            rows.append(
                {
                    "name": c["name"],
                    "kind": c.get("kind", "role"),
                    "weight": c.get("weight", 0),
                    "score": s.score,
                    "comment": s.comment,
                }
            )
    total_weight = sum(r["weight"] for r in rows)
    if not rows or total_weight <= 0:
        # The model renamed every criterion: fall back to a plain average.
        rows = [
            {
                "name": s.name,
                "kind": "role",
                "weight": 0,
                "score": s.score,
                "comment": s.comment,
            }
            for s in scores
        ]
        return round(sum(s.score for s in scores) / len(scores), 2), rows
    score = sum(r["score"] * r["weight"] for r in rows) / total_weight
    return round(score, 2), rows


def verdict_for(score: float) -> str:
    return next(v for floor, v in VERDICTS if score >= floor)


def target_words(budget_sec: int | None) -> int:
    """Length of the stronger version: ~70% of what fits the budget at 130 wpm."""
    return min(250, max(80, round((budget_sec or 120) * 130 / 60 * 0.7)))


def section_module(session: Session, section: str) -> str:
    for s in (session.plan_json or {}).get("sections", []):
        if s["name"] == section:
            return s.get("module", "behavioral")
    return "behavioral"


def evaluate(
    user_id: int,
    session: Session,
    answer_id: int,
    section: str,
    budget_sec: int | None,
    exchange: list[dict],
    clips: list[Clip],
) -> Evaluation:
    """One Fire chat call → a saved Evaluation for `answer_id`.

    `exchange` is [{"interviewer": ..., "candidate": ...}], main question first.
    """
    resume = db.session.get(Document, session.resume_id) if session.resume_id else None
    prompt = render(
        "score",
        role=(session.plan_json or {}).get("role_title") or "the role",
        difficulty=session.difficulty or "mid",
        module=section_module(session, section).replace("_", " "),
        rubric=[
            {k: c.get(k, "") for k in ("name", "description", "strong_answer")}
            for c in (session.rubric_json or {}).get("criteria", [])
        ],
        resume=(resume.raw_text if resume else "(not available)")[:MAX_RESUME_CHARS],
        exchange=exchange,
        target_words=str(target_words(budget_sec)),
    )
    out = chat_json(user_id, prompt, ScoreOut, SYSTEM, max_tokens=2000, temperature=0.3)
    score, rows = weighted_score(out.criteria, session.rubric_json)

    said = _norm(" ".join(e["candidate"] for e in exchange))
    weak = [w.model_dump() for w in out.weak_moments if _norm(w.quote) in said][:3]
    evaluation = Evaluation(
        answer_id=answer_id,
        score=score,
        rubric_scores_json={"criteria": rows},
        missing_points_json=[m.model_dump() for m in out.missing_points],
        stronger_version=out.stronger_version.strip(),
        changes_json=[c.model_dump() for c in out.changes],
        delivery_json=delivery(clips, budget_sec),
        feedback_json={
            "summary": out.summary,
            "weak_moments": weak,
            "star": out.star.model_dump() if out.star else None,
            "tips": [t for t in out.tips if t.strip()][:2],
        },
    )
    db.session.add(evaluation)
    db.session.commit()
    return evaluation


def evaluation_dict(e: Evaluation | None) -> dict | None:
    if e is None:
        return None
    fb = e.feedback_json or {}
    return {
        "score": e.score,
        "criteria": (e.rubric_scores_json or {}).get("criteria", []),
        "summary": fb.get("summary", ""),
        "weak_moments": fb.get("weak_moments", []),
        "star": fb.get("star"),
        "tips": fb.get("tips", []),
        "missing_points": e.missing_points_json or [],
        "stronger_version": e.stronger_version,
        "changes": e.changes_json or [],
        "delivery": e.delivery_json,
    }
