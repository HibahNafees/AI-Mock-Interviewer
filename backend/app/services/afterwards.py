"""After the interview: a one-page cheat sheet (no Fire call; built only from the
user's own data, so nothing is invented) and a drafted thank-you email (one call)."""

import re

from pydantic import BaseModel, Field

from ..extensions import db
from ..models import (
    Answer,
    Debrief,
    GapAnalysis,
    JdAnalysis,
    Question,
    Report,
    Session,
    Story,
    User,
)
from . import reports, stories
from .llm import chat_json, render
from .scoring import SYSTEM

# Sentence ends: punctuation followed by a space (so "1.8 s" isn't split).
SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+|\n+")
DIGIT_RE = re.compile(r"\d")
MAX_NUMBERS = 6


def _company(session: Session) -> str | None:
    d = db.session.scalar(db.select(Debrief).filter_by(session_id=session.id))
    return d.company if d else None


def _key_numbers(texts: list[str]) -> list[str]:
    """Sentences from their own words that carry a number ('p95 1.8 s → 300 ms')."""
    out: list[str] = []
    seen = set()
    for t in texts:
        for m in [x for x in SENTENCE_END_RE.split(t or "") if DIGIT_RE.search(x)]:
            s = " ".join(m.split()).strip(" ,;")
            key = re.sub(r"\W+", "", s.lower())
            if 12 <= len(s) <= 200 and key not in seen:
                seen.add(key)
                out.append(s)
    return out[:MAX_NUMBERS]


def cheat_sheet(session: Session, report: Report) -> dict:
    plan = session.plan_json or {}
    view = reports.report_dict(session, report)
    job = [
        c["name"]
        for c in (session.rubric_json or {}).get("criteria", [])
        if c.get("kind", "role") == "role"
    ]
    mine = db.session.scalars(db.select(Story).filter_by(user_id=session.user_id)).all()
    ranked = sorted(
        mine,
        key=lambda s: (
            -sum(1 for n in job if stories._matches(n, s)),
            -(s.strength or 0),
        ),
    )[:3]
    answers = [
        a.transcript
        for a in db.session.scalars(
            db.select(Answer)
            .join(Question, Answer.question_id == Question.id)
            .where(Question.session_id == session.id, Answer.attempt_no == 1)
        )
    ]
    star_texts = [
        " ".join(v for v in (s.star_json or {}).values() if v) for s in ranked
    ]
    weak = (
        [c for c in view["competencies"] if c["score"] < 3.5][-3:]
        if view["competencies"]
        else []
    )
    likely = []
    if session.jd_id and session.resume_id:
        gaps = db.session.scalar(
            db.select(GapAnalysis).filter_by(
                resume_id=session.resume_id, jd_id=session.jd_id
            )
        )
        if gaps:
            likely = [
                r["likely_question"]
                for r in gaps.result_json["requirements"]
                if r["status"] != "covered" and r["likely_question"]
            ][:3]
    to_ask = []
    if plan.get("jd_analysis_id"):
        a = db.session.get(JdAnalysis, plan["jd_analysis_id"])
        to_ask = (
            [
                q["question"]
                for q in ((a.decoder_json or {}).get("questions_to_ask") or {}).get(
                    "questions", []
                )
            ][:3]
            if a
            else []
        )
    return {
        "role_title": plan.get("role_title") or "Interview",
        "company": _company(session),
        "stories": [
            {
                "title": s.title,
                "action": (s.star_json or {}).get("action"),
                "result": (s.star_json or {}).get("result"),
                "fits": [n for n in job if stories._matches(n, s)],
            }
            for s in ranked
        ],
        "key_numbers": _key_numbers(star_texts + answers),
        "weak_spots": [{"name": c["name"], "score": c["score"]} for c in weak],
        "takeaways": view["takeaways"],
        "likely_questions": likely or [u["text"] for u in view["unanswered"]][:3],
        "questions_to_ask": to_ask,
    }


class EmailOut(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=20, max_length=2000)


def thank_you(user_id: int, session: Session, report: Report) -> dict:
    plan = session.plan_json or {}
    if plan.get("thank_you"):
        return plan["thank_you"]
    user = db.session.get(User, session.user_id)
    view = reports.report_dict(session, report)
    topics = [q["text"] for q in view["questions"]][:5]
    highlights = [
        s
        for q in view["questions"]
        if q["evaluation"]
        for s in (q["evaluation"].get("strengths") or [])[:1]
    ][:2]
    out = chat_json(
        user_id,
        render(
            "thank_you",
            name=(user.name if user else "").split(" ")[0] or "[Your name]",
            role=plan.get("role_title") or "the role",
            company=_company(session) or "unknown",
            topics=topics,
            highlights=highlights,
        ),
        EmailOut,
        SYSTEM,
        max_tokens=600,
        temperature=0.5,
    )
    email = {"subject": out.subject.strip(), "body": out.body.strip()}
    session.plan_json = {**plan, "thank_you": email}
    db.session.commit()
    return email
