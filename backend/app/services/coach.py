"""Questions-for-them coach: questions to ask at the end, and ratings for the ones
asked in the interview's "Do you have any questions for me?" step."""

from typing import Literal

from pydantic import BaseModel, Field

from ..extensions import db
from ..models import Answer, Document, Question, Session
from . import planning
from .llm import chat_json, render
from .scoring import SYSTEM

MAX_JD_CHARS = 6000


class Suggestion(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    why: str = Field(default="", max_length=300)
    topic: Literal["role", "team", "growth", "process", "company"] = "role"


class SuggestionsOut(BaseModel):
    questions: list[Suggestion] = Field(min_length=1, max_length=10)
    avoid: list[str] = Field(default_factory=list, max_length=4)


class Rated(BaseModel):
    asked: str = Field(min_length=1, max_length=600)
    score: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=300)
    better: str | None = Field(default=None, max_length=400)


class RatedOut(BaseModel):
    questions: list[Rated] = Field(default_factory=list, max_length=5)
    summary: str = Field(default="", max_length=400)


def questions_to_ask(user_id: int, jd: Document) -> dict:
    """Suggestions for a job (one Fire call, kept with the job's analysis)."""
    analysis = planning.analyze_jd(user_id, jd)
    extra = analysis.decoder_json or {}
    if extra.get("questions_to_ask"):
        return extra["questions_to_ask"]
    out = chat_json(
        user_id,
        render(
            "questions_to_ask",
            analysis=planning.analysis_summary(analysis),
            jd=jd.raw_text[:MAX_JD_CHARS],
        ),
        SuggestionsOut,
        SYSTEM,
        max_tokens=1000,
        temperature=0.5,
    )
    result = {
        "questions": [q.model_dump() for q in out.questions][:8],
        "avoid": [a.strip() for a in out.avoid if a.strip()][:3],
    }
    analysis.decoder_json = {**extra, "questions_to_ask": result}
    db.session.commit()
    return result


def their_turns(session: Session) -> list[str]:
    """What the candidate said in the "any questions for me?" step."""
    return [
        a.transcript
        for a in db.session.scalars(
            db.select(Answer)
            .join(Question, Answer.question_id == Question.id)
            .where(
                Question.session_id == session.id, Question.is_candidate_qa.is_(True)
            )
            .order_by(Question.order_no, Question.id)
        )
    ]


def rate_their_questions(user_id: int, session: Session) -> dict | None:
    """Ratings for the questions they asked (one Fire call; none if they asked none)."""
    turns = [t for t in their_turns(session) if "?" in t]
    if not turns:
        return None
    out = chat_json(
        user_id,
        render(
            "rate_their_questions",
            role=(session.plan_json or {}).get("role_title") or "the role",
            turns=turns,
        ),
        RatedOut,
        SYSTEM,
        max_tokens=900,
        temperature=0,
    )
    said = " ".join(turns).lower()
    rated = [
        q.model_dump()
        for q in out.questions
        if q.asked.strip().lower()[:40] in said  # only questions they really asked
    ]
    return {"questions": rated, "summary": out.summary.strip()} if rated else None
