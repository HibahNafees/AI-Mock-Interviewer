"""Reverse mode: the user interviews an AI candidate with a hidden profile,
decides hire / no hire, then sees the profile and feedback on their interviewing.

The hidden profile never leaves the server until the decision is made.
"""

import random

from pydantic import BaseModel, Field

from ..extensions import db
from ..models import Answer, Document, Question, Session
from ..models.base import utcnow
from . import planning
from .llm import chat_json, render

PROFILES = ("strong", "average", "weak", "exaggerating")
MAX_QUESTIONS = 15
SECTION = "Reverse interview"
# What a sound decision usually is, by type ("either" = reasons decide).
EXPECTED = {
    "strong": "hire",
    "average": "either",
    "weak": "no_hire",
    "exaggerating": "no_hire",
}


class HiddenOut(BaseModel):
    truths: list[str] = Field(default_factory=list, max_length=8)
    exaggerations: list[str] = Field(default_factory=list, max_length=6)
    strengths: list[str] = Field(default_factory=list, max_length=4)
    weaknesses: list[str] = Field(default_factory=list, max_length=4)
    answer_style: str = Field(default="", max_length=300)


class CandidateOut(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    headline: str = Field(min_length=1, max_length=160)
    resume: list[str] = Field(min_length=2, max_length=8)
    hidden: HiddenOut


class AnswerOut(BaseModel):
    answer: str = Field(min_length=1, max_length=1500)


class Scored(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=600)


class QuestionFeedback(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    score: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=400)


class JudgeOut(BaseModel):
    judgment: Scored
    questioning: Scored
    question_feedback: list[QuestionFeedback] = Field(
        default_factory=list, max_length=15
    )
    missed_signals: list[str] = Field(default_factory=list, max_length=6)
    good_moves: list[str] = Field(default_factory=list, max_length=6)
    unfair_questions: list[str] = Field(default_factory=list, max_length=6)
    tips: list[str] = Field(default_factory=list, max_length=3)


class ReverseError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


def _state(session: Session) -> dict:
    return (session.plan_json or {}).get("reverse") or {}


def start(user_id: int, jd: Document, profile: str, duration_min: int) -> Session:
    analysis = planning.analyze_jd(user_id, jd)
    summary = planning.analysis_summary(analysis)
    if profile not in PROFILES:
        profile = random.choice(PROFILES)  # "surprise me"
    cand = chat_json(
        user_id,
        render("reverse_candidate", analysis=summary, profile=profile),
        CandidateOut,
        max_tokens=1200,
        temperature=0.8,
    )
    now = utcnow()
    session = Session(
        user_id=user_id,
        jd_id=jd.id,
        mode="reverse",
        duration_min=duration_min,
        difficulty=summary.get("seniority") or "mid",
        persona="neutral",
        status="active",
        started_at=now,
        plan_json={
            "role_title": summary.get("role_title") or "the role",
            "analysis": summary,
            "reverse": {
                "profile": profile,
                "name": cand.name.strip(),
                "headline": cand.headline.strip(),
                "resume": [r.strip() for r in cand.resume if r.strip()],
                "hidden": cand.hidden.model_dump(),
            },
        },
    )
    db.session.add(session)
    db.session.commit()
    return session


def _transcript(session: Session) -> list[dict]:
    rows = db.session.execute(
        db.select(Question, Answer)
        .join(Answer, Answer.question_id == Question.id)
        .where(Question.session_id == session.id)
        .order_by(Question.order_no)
    ).all()
    return [
        {"question": q.asked_text, "answer": a.transcript, "input_mode": a.input_mode}
        for q, a in rows
    ]


def ask(user_id: int, session: Session, text: str, input_mode: str) -> dict:
    """The user's question → the candidate's in-character answer."""
    if session.status != "active":
        raise ReverseError("This interview is over")
    history = _transcript(session)
    if len(history) >= MAX_QUESTIONS:
        raise ReverseError(
            f"That's {MAX_QUESTIONS} questions: time to make your decision."
        )
    st = _state(session)
    out = chat_json(
        user_id,
        render(
            "reverse_answer",
            candidate=st["name"],
            role=(session.plan_json or {}).get("role_title") or "the role",
            resume=st["resume"],
            hidden=st["hidden"],
            profile=st["profile"],
            history=history[-10:],
            question=text,
        ),
        AnswerOut,
        max_tokens=400,
        temperature=0.7,
    )
    q = Question(
        session_id=session.id,
        section=SECTION,
        order_no=len(history) + 1,
        text=text,
        asked_text=text,
        asked_at=utcnow(),
        is_bonus=False,
    )
    db.session.add(q)
    db.session.flush()
    db.session.add(
        Answer(
            question_id=q.id,
            transcript=out.answer.strip(),
            attempt_no=1,
            input_mode=input_mode,
        )
    )
    db.session.commit()
    return {"question": text, "answer": out.answer.strip()}


def decide(user_id: int, session: Session, decision: str, reasons: str) -> dict:
    if session.status != "active":
        raise ReverseError("You've already made your decision")
    transcript = _transcript(session)
    if not transcript:
        raise ReverseError("Ask the candidate at least one question first")
    st = _state(session)
    out = chat_json(
        user_id,
        render(
            "reverse_judge",
            role=(session.plan_json or {}).get("role_title") or "the role",
            profile=st["profile"],
            hidden=st["hidden"],
            resume=st["resume"],
            transcript=transcript,
            decision="hire" if decision == "hire" else "no hire",
            reasons=reasons,
        ),
        JudgeOut,
        max_tokens=1800,
        temperature=0,
    )
    expected = EXPECTED[st["profile"]]
    result = {
        "decision": decision,
        "reasons": reasons,
        "expected": expected,
        # Fixed by the hidden type, except "average" where the reasons decide.
        "decision_matches": expected == "either" or expected == decision,
        **out.model_dump(),
    }
    session.plan_json = {
        **(session.plan_json or {}),
        "reverse": {**st, "result": result},
    }
    session.status = "completed"
    session.ended_at = utcnow()
    db.session.commit()
    return result


def view(session: Session) -> dict:
    """What the browser may see: the hidden profile only after the decision."""
    st = _state(session)
    done = session.status == "completed" and "result" in st
    return {
        "id": session.id,
        "status": session.status,
        "role_title": (session.plan_json or {}).get("role_title"),
        "duration_min": session.duration_min,
        "started_at": (
            session.started_at.isoformat() + "Z" if session.started_at else None
        ),
        "candidate": {
            "name": st.get("name"),
            "headline": st.get("headline"),
            "resume": st.get("resume", []),
        },
        "transcript": _transcript(session),
        "max_questions": MAX_QUESTIONS,
        "reveal": (
            {"profile": st["profile"], "hidden": st["hidden"], "result": st["result"]}
            if done
            else None
        ),
    }
