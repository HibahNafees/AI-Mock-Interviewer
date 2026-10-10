"""Post-interview reports: built question by question in a background thread.

Each question is scored as soon as possible and committed, so the report page fills
in progressively. A failed run keeps what it finished; requesting the report again
only pays for the missing parts.
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import timedelta

from flask import current_app
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Answer, Evaluation, Question, Report, Session
from ..models.base import utcnow
from . import interviewer, practice, scoring, stories
from .analytics import Clip, delivery, session_summary
from .fire import FireError
from .limits import LimitReached, check_budget
from .llm import chat_json, render

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=10)


class SummaryOut(BaseModel):
    reasoning: str = Field(min_length=1, max_length=1200)
    takeaways: list[str] = Field(min_length=1, max_length=5)
    exercises: list[str] = Field(default_factory=list, max_length=4)


@dataclass
class Thread:
    """A planned (or bonus) question with its follow-ups, in the order asked."""

    root: Question
    asked: list[Question]
    answers: dict[int, Answer]  # question id → first-attempt answer
    retries: list[Answer] = field(default_factory=list)

    @property
    def main_answer(self) -> Answer | None:
        return self.answers.get(self.root.id)

    def exchange(self) -> list[dict]:
        return [
            {
                "interviewer": (q.asked_text or q.text)[:1000],
                "candidate": self.answers[q.id].transcript,
                "spoken": self.answers[q.id].input_mode == "voice",
                **({"hint": q.hint_text} if q.hint_text else {}),
            }
            for q in self.asked
            if q.id in self.answers
        ]

    def clips(self) -> list[Clip]:
        return [
            Clip(a.transcript, a.duration_ms, a.input_mode)
            for q in self.asked
            if (a := self.answers.get(q.id)) is not None
        ]


def threads(session: Session) -> list[Thread]:
    """Answered questions grouped with their follow-ups, in interview order."""
    asked = interviewer.asked_questions(session)
    rows = db.session.scalars(
        db.select(Answer)
        .where(Answer.question_id.in_([q.id for q in asked]))
        .order_by(Answer.attempt_no, Answer.id)
    ).all()
    first = {a.question_id: a for a in rows if a.attempt_no == 1}
    out = []
    for q in asked:
        if (
            q.follow_up_of_id is not None
            or q.id not in first
            or q.is_icebreaker
            or q.is_candidate_qa
        ):
            continue
        group = [q] + [f for f in asked if f.follow_up_of_id == q.id]
        out.append(
            Thread(
                root=q,
                asked=group,
                answers={g.id: first[g.id] for g in group if g.id in first},
                retries=[a for a in rows if a.question_id == q.id and a.attempt_no > 1],
            )
        )
    return out


def evaluations_for(answer_ids: list[int]) -> dict[int, Evaluation]:
    if not answer_ids:
        return {}
    return {
        e.answer_id: e
        for e in db.session.scalars(
            db.select(Evaluation)
            .where(Evaluation.answer_id.in_(answer_ids))
            .order_by(Evaluation.id)
        )
    }


def get_report(session: Session) -> Report | None:
    return db.session.scalar(db.select(Report).filter_by(session_id=session.id))


def request_report(session: Session) -> Report:
    """Create the report (or resume a failed/stale run) and generate it."""
    report = get_report(session)
    if report is not None:
        if report.status == "ready":
            if report.stories_at is None:
                # The story bank update failed last time: try it again.
                _launch(report.id, session.user_id)
            return report
        fresh = report.started_at and utcnow() - report.started_at < STALE_AFTER
        if report.status == "generating" and fresh:
            return report
    check_budget()
    if report is None:
        report = Report(session_id=session.id)
        db.session.add(report)
    report.status = "generating"
    report.started_at = utcnow()
    try:
        db.session.commit()
    except IntegrityError:
        # Another request created it first; that one generates.
        db.session.rollback()
        return get_report(session)
    _launch(report.id, session.user_id)
    return report


def _launch(report_id: int, user_id: int) -> None:
    app = current_app._get_current_object()
    if app.config.get("REPORTS_INLINE"):
        generate(report_id, user_id)
        return

    def run():
        with app.app_context():
            try:
                generate(report_id, user_id)
            except Exception:
                log.exception("Report %s failed", report_id)
                db.session.rollback()
                report = db.session.get(Report, report_id)
                if report is not None:
                    report.status = "failed"
                    db.session.commit()

    threading.Thread(target=run, name=f"report-{report_id}", daemon=True).start()


def generate(report_id: int, user_id: int) -> None:
    report = db.session.get(Report, report_id)
    session = db.session.get(Session, report.session_id)
    items = threads(session)
    done = evaluations_for([t.main_answer.id for t in items])
    failed = False
    for t in items:
        if t.main_answer.id in done:
            continue
        try:
            done[t.main_answer.id] = scoring.evaluate(
                user_id,
                session,
                t.main_answer.id,
                t.root.section,
                t.root.budget_sec,
                t.exchange(),
                t.clips(),
                question=t.root.text,
            )
        except (FireError, LimitReached) as err:
            log.warning("Scoring question %s failed: %s", t.root.id, err)
            db.session.rollback()
            failed = True

    per_question = [delivery(t.clips(), t.root.budget_sec) for t in items]
    report.analytics_json = session_summary(per_question)
    scored = [done[t.main_answer.id] for t in items if t.main_answer.id in done]
    if scored:
        report.overall_score = round(sum(e.score for e in scored) / len(scored), 2)
        report.verdict = scoring.verdict_for(report.overall_score)
    if failed or not scored:
        report.status = "failed" if items else "ready"
        db.session.commit()
        return

    if not report.top_takeaways_json:
        try:
            summary = _summarize(user_id, session, report, items, done)
        except (FireError, LimitReached) as err:
            log.warning("Report summary %s failed: %s", report.id, err)
            db.session.rollback()
            report.status = "failed"
            db.session.commit()
            return
        report.verdict_reason = summary.reasoning
        report.top_takeaways_json = [t for t in summary.takeaways if t.strip()][:3]
        report.exercises_json = [x for x in summary.exercises if x.strip()][:3]
        # Once, when the report is first complete: missed questions join the bank.
        practice.record_session(
            user_id,
            session,
            items,
            done,
            lambda section: scoring.section_module(session, section),
        )
    report.status = "ready"
    db.session.commit()
    _update_story_bank(user_id, session, report, items, done)


def _update_story_bank(user_id, session, report, items, done) -> None:
    """Once per session, after the report is safe: a failure here never fails it."""
    if report.stories_at is not None:
        return
    scores = {
        t.root.id: done[t.main_answer.id].score
        for t in items
        if t.main_answer.id in done
    }
    try:
        stories.extract(user_id, session, items, scores)
    except (FireError, LimitReached) as err:
        log.warning("Story extraction for session %s failed: %s", session.id, err)
        db.session.rollback()
        return
    report.stories_at = utcnow()
    db.session.commit()


def _summarize(user_id, session, report, items, done) -> SummaryOut:
    questions = []
    for t in items:
        e = done[t.main_answer.id]
        questions.append(
            {
                "question": t.root.text[:300],
                "score": e.score,
                "summary": (e.feedback_json or {}).get("summary", ""),
                "missed": [
                    m["point"]
                    for m in (e.missing_points_json or [])
                    if not m["covered"]
                ][:3],
            }
        )
    prompt = render(
        "report_summary",
        role=(session.plan_json or {}).get("role_title") or "the role",
        difficulty=session.difficulty or "mid",
        overall=f"{report.overall_score:.1f}",
        verdict=report.verdict,
        questions=questions,
        delivery=report.analytics_json,
    )
    return chat_json(user_id, prompt, SummaryOut, scoring.SYSTEM, max_tokens=600)


# ---- "Try again" ----------------------------------------------------------


def retry(
    user_id: int,
    session: Session,
    question: Question,
    text: str,
    duration_ms: int | None,
    input_mode: str,
) -> Answer:
    """Save a new attempt at a planned question and score it on its own."""
    attempts = db.session.scalar(
        db.select(db.func.max(Answer.attempt_no)).filter_by(question_id=question.id)
    )
    answer = Answer(
        question_id=question.id,
        transcript=text,
        duration_ms=duration_ms,
        attempt_no=(attempts or 1) + 1,
        input_mode=input_mode,
    )
    db.session.add(answer)
    db.session.flush()
    exchange = [
        {
            "interviewer": question.text,
            "candidate": text,
            "spoken": input_mode == "voice",
        }
    ]
    # Score on the same criteria as the first attempt (T-29: the first answer was
    # scored on 3 criteria and the retry on 6, so a better retry scored lower).
    first = db.session.scalar(
        db.select(Evaluation)
        .join(Answer, Evaluation.answer_id == Answer.id)
        .where(Answer.question_id == question.id, Answer.attempt_no == 1)
    )
    rows = (first.rubric_scores_json or {}).get("criteria", []) if first else []
    criteria = [c["name"] for c in rows if c.get("score") is not None]
    first_answer = db.session.get(Answer, first.answer_id) if first else None
    # The scorer sees the first attempt, so a retry that fixes its weaknesses scores
    # higher and a reworded copy scores the same (T-29).
    previous = (
        {
            "answer": first_answer.transcript if first_answer else "",
            "criteria": [
                {
                    "name": c["name"],
                    "score": c["score"],
                    "comment": c.get("comment", ""),
                }
                for c in rows
                if c.get("score") is not None
            ],
            "summary": (first.feedback_json or {}).get("summary", ""),
        }
        if first
        else None
    )
    try:
        evaluation = scoring.evaluate(
            user_id,
            session,
            answer.id,
            question.section,
            question.budget_sec,
            exchange,
            [Clip(text, duration_ms, input_mode)],
            question=question.text,
            criteria=criteria or None,
            previous=previous,
        )
    except (FireError, LimitReached):
        # Fire spend is committed along the way; don't keep an unscored attempt.
        db.session.rollback()
        orphan = db.session.get(Answer, answer.id)
        if orphan is not None:
            db.session.delete(orphan)
            db.session.commit()
        raise
    module = scoring.section_module(session, question.section)
    if module != "roleplay":
        # Practicing a question again counts as a review in the question bank.
        practice.review(
            user_id, session, question.text, question.section, module, evaluation
        )
        db.session.commit()
    return answer


# ---- Views ---------------------------------------------------------------


def competencies(evals: list[Evaluation]) -> list[dict]:
    """Each rubric criterion averaged over the questions that tested it."""
    rows: dict[str, dict] = {}
    for e in evals:
        for c in (e.rubric_scores_json or {}).get("criteria", []):
            if c.get("score") is None:
                continue
            row = rows.setdefault(
                c["name"].strip().lower(),
                {
                    "name": c["name"].strip(),
                    "kind": c.get("kind", "role"),
                    "scores": [],
                },
            )
            row["scores"].append(c["score"])
    out = [
        {
            "name": r["name"],
            "kind": r["kind"],
            "score": round(sum(r["scores"]) / len(r["scores"]), 2),
            "questions": len(r["scores"]),
        }
        for r in rows.values()
    ]
    # Job-specific criteria first, then the communication basics.
    return sorted(out, key=lambda r: (r["kind"] != "role", -r["score"]))


def unanswered(session: Session, items: list["Thread"]) -> list[dict]:
    """Planned questions the interview never got to, or that got no answer."""
    answered = {t.root.id for t in items}
    rows = db.session.scalars(
        db.select(Question)
        .filter_by(
            session_id=session.id,
            follow_up_of_id=None,
            is_bonus=False,
            is_icebreaker=False,
            is_candidate_qa=False,
        )
        .order_by(Question.order_no, Question.id)
    )
    return [
        {"text": q.text, "section": q.section, "asked": q.asked_at is not None}
        for q in rows
        if q.id not in answered
    ]


def report_dict(session: Session, report: Report) -> dict:
    items = threads(session)
    answer_ids = [t.main_answer.id for t in items] + [
        a.id for t in items for a in t.retries
    ]
    evals = evaluations_for(answer_ids)
    questions = []
    for t in items:
        main = t.main_answer
        e = evals.get(main.id)
        questions.append(
            {
                "question_id": t.root.id,
                "section": t.root.section,
                "module": scoring.section_module(session, t.root.section),
                "scenario": scoring.section_plan(session, t.root.section).get(
                    "scenario"
                ),
                "text": t.root.text,
                "is_bonus": t.root.is_bonus,
                "budget_sec": t.root.budget_sec,
                "exchange": [
                    {
                        "interviewer": q.asked_text or q.text,
                        "answer": t.answers[q.id].transcript,
                        "is_follow_up": q.follow_up_of_id is not None,
                        "input_mode": t.answers[q.id].input_mode,
                    }
                    for q in t.asked
                    if q.id in t.answers
                ],
                "delivery": (
                    e.delivery_json if e else delivery(t.clips(), t.root.budget_sec)
                ),
                "evaluation": scoring.evaluation_dict(e),
                "attempts": [
                    {
                        "attempt_no": a.attempt_no,
                        "answer": a.transcript,
                        "input_mode": a.input_mode,
                        "evaluation": scoring.evaluation_dict(evals.get(a.id)),
                    }
                    for a in t.retries
                ],
            }
        )
    analysis = (session.plan_json or {}).get("analysis") or {}
    return {
        "session_id": session.id,
        "status": report.status,
        "role_title": (session.plan_json or {}).get("role_title", ""),
        "duration_min": session.duration_min,
        "difficulty": session.difficulty,
        "licensed_field": bool(analysis.get("licensed_field")),
        "overall_score": report.overall_score,
        "verdict": report.verdict,
        "verdict_reason": report.verdict_reason,
        "takeaways": report.top_takeaways_json or [],
        "exercises": report.exercises_json or [],
        "competencies": competencies(
            [evals[t.main_answer.id] for t in items if t.main_answer.id in evals]
        ),
        "unanswered": unanswered(session, items),
        "analytics": report.analytics_json,
        "progress": {
            "scored": sum(1 for t in items if t.main_answer.id in evals),
            "total": len(items),
        },
        "questions": questions,
    }
