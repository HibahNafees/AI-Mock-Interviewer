"""Question bank with spaced repetition, and weak-spot practice interviews.

Questions scored under 4 go into the user's bank and come back later; scoring 4+
twice in a row masters them. No Fire calls: a weak-spot interview reuses the
source session's résumé, job description and rubric.
"""

from datetime import timedelta

from ..extensions import db
from ..models import QuestionBankItem, Session
from ..models.base import utcnow
from .planning import PlanOut, PlanSectionOut, save_plan

GOOD = 4.0  # at or above: the answer is solid
MASTER_REVIEWS = 2  # good reviews in a row to master a question
MAX_INTERVAL_DAYS = 60
PRACTICE_SECTION = "Weak spots"


def first_interval(score: float) -> int:
    """Days until a missed question comes back: weaker answers return sooner."""
    if score < 2.5:
        return 1
    if score < 3.5:
        return 3
    return 7


def _key(text: str) -> str:
    return " ".join(text.lower().split())


def _weakest(evaluation) -> str | None:
    rows = [
        c
        for c in (evaluation.rubric_scores_json or {}).get("criteria", [])
        if c.get("score") is not None
    ]
    role = [c for c in rows if c.get("kind", "role") == "role"] or rows
    return min(role, key=lambda c: c["score"])["name"] if role else None


def review(
    user_id: int,
    session: Session,
    question_text: str,
    section: str,
    module: str,
    evaluation,
) -> QuestionBankItem | None:
    """Record one scored answer: add a missed question, or reschedule a known one."""
    now = utcnow()
    score = evaluation.score
    item = next(
        (
            i
            for i in db.session.scalars(
                db.select(QuestionBankItem)
                .filter_by(user_id=user_id)
                .where(QuestionBankItem.mastered_at.is_(None))
            )
            if _key(i.question_text) == _key(question_text)
        ),
        None,
    )
    if item is None:
        if score >= GOOD:
            return None  # answered well the first time: nothing to practice
        item = QuestionBankItem(
            user_id=user_id,
            question_text=question_text.strip(),
            source_session_id=session.id,
            section=section,
            module=module,
            interval_days=first_interval(score),
            reviews=0,
        )
        db.session.add(item)
    elif score >= GOOD:
        item.reviews += 1
        if item.reviews >= MASTER_REVIEWS:
            item.mastered_at = now
            item.next_review_at = None
        else:
            item.interval_days = min(MAX_INTERVAL_DAYS, max(7, item.interval_days * 2))
    else:
        item.reviews = 0  # missed again: start over
        item.interval_days = first_interval(score)
    item.last_score = score
    item.competency = _weakest(evaluation) or item.competency
    if item.mastered_at is None:
        item.next_review_at = now + timedelta(days=item.interval_days)
    return item


def record_session(
    user_id: int, session: Session, threads: list, evals: dict, module_of
) -> None:
    """After a report: every scored planned question updates the bank."""
    for t in threads:
        e = evals.get(t.main_answer.id)
        module = module_of(t.root.section)
        if e is None or module == "roleplay":
            continue  # role-play openers only make sense inside their scenario
        review(user_id, session, t.root.text, t.root.section, module, e)
    db.session.commit()


def queue(user_id: int) -> dict:
    now = utcnow()
    items = db.session.scalars(
        db.select(QuestionBankItem)
        .filter_by(user_id=user_id)
        .order_by(QuestionBankItem.next_review_at)
    ).all()
    active = [i for i in items if i.mastered_at is None]
    return {
        "due": [
            item_dict(i) for i in active if i.next_review_at and i.next_review_at <= now
        ],
        "upcoming": [
            item_dict(i) for i in active if i.next_review_at and i.next_review_at > now
        ],
        "mastered": sum(1 for i in items if i.mastered_at is not None),
    }


def item_dict(i: QuestionBankItem) -> dict:
    source = (
        db.session.get(Session, i.source_session_id) if i.source_session_id else None
    )
    return {
        "id": i.id,
        "question": i.question_text,
        "competency": i.competency,
        "last_score": i.last_score,
        "next_review_at": (
            i.next_review_at.isoformat() + "Z" if i.next_review_at else None
        ),
        "role": (source.plan_json or {}).get("role_title") if source else None,
    }


def questions_for(duration_min: int) -> int:
    return max(2, min(6, duration_min // 3))


def build_session(user_id: int, duration_min: int) -> Session | None:
    """A planned interview from the due (then weakest) bank questions of one job."""
    now = utcnow()
    items = db.session.scalars(
        db.select(QuestionBankItem)
        .filter_by(user_id=user_id)
        .where(QuestionBankItem.mastered_at.is_(None))
        .where(QuestionBankItem.source_session_id.is_not(None))
    ).all()
    if not items:
        return None
    items.sort(
        key=lambda i: (
            not (i.next_review_at and i.next_review_at <= now),
            i.next_review_at or now,
            i.last_score or 0,
        )
    )
    source = db.session.get(Session, items[0].source_session_id)
    same_job = [
        i
        for i in items
        if (s := db.session.get(Session, i.source_session_id))
        and s.jd_id == source.jd_id
    ][: questions_for(duration_min)]
    module = same_job[0].module or "behavioral"
    plan = source.plan_json or {}
    session = Session(
        user_id=user_id,
        resume_id=source.resume_id,
        jd_id=source.jd_id,
        mode="standard",
        duration_min=duration_min,
        difficulty=source.difficulty,
        persona=source.persona,
        status="planned",
        rubric_json=source.rubric_json,
        plan_json={
            "analysis": plan.get("analysis"),
            "jd_analysis_id": plan.get("jd_analysis_id"),
            "focus": "mixed",
            "practice": True,
        },
    )
    db.session.add(session)
    db.session.flush()
    save_plan(
        session,
        PlanOut(
            sections=[
                PlanSectionOut(
                    name=PRACTICE_SECTION,
                    module=module,
                    minutes=duration_min,
                    questions=[i.question_text for i in same_job],
                )
            ],
            reserve=[],
        ),
        role_title=plan.get("role_title", ""),
    )
    return session
