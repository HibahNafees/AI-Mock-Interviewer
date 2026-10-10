"""Story bank: reusable STAR stories extracted from the user's own answers.

One Fire chat call per session (after its report). Every STAR part must come from
what the candidate said; anything that isn't backed by their answers is dropped and
shown as a gap, never filled in (docs/INTERVIEWER_RULES.md, Story Bank).
"""

import logging
import re

from pydantic import BaseModel, Field

from ..extensions import db
from ..models import Answer, JdAnalysis, Question, Session, Story
from ..models.base import utcnow
from .llm import chat_json, render
from .scoring import HYPOTHETICAL_RE, SYSTEM, Sentence, grounding_problems

log = logging.getLogger(__name__)

PARTS = ("situation", "task", "action", "result")
# The story types most interviews probe; a gap here is worth a nudge.
CORE_COMPETENCIES = [
    "Leadership",
    "Teamwork",
    "Conflict",
    "Failure and learning",
    "Problem solving",
    "Ownership",
    "Communication",
    "Impact and results",
]
MIN_WORDS = 30  # less than this in a whole session: nothing worth extracting
SAME_STORY = 0.6
WORD_RE = re.compile(r"[a-z]+")
FILLER = frozenset(
    """the a an and or to of in on for with my our we i it was were that this at by
    from as so then them they their his her be been is are had has have did""".split()
)


class StoryOut(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    situation: str | None = Field(default=None, max_length=600)
    task: str | None = Field(default=None, max_length=600)
    action: str | None = Field(default=None, max_length=800)
    result: str | None = Field(default=None, max_length=600)
    competencies: list[str] = Field(default_factory=list, max_length=6)
    answer_ids: list[int] = Field(default_factory=list, max_length=12)
    same_as: int | None = None


class StoriesOut(BaseModel):
    stories: list[StoryOut] = Field(default_factory=list, max_length=6)


def _words(text: str) -> set[str]:
    return {w[:6] for w in WORD_RE.findall((text or "").lower()) if w not in FILLER}


def _same_story(a: Story, b: StoryOut) -> bool:
    """Same experience told twice (title + what they did), in different words."""
    wa = _words(f"{a.title} {(a.star_json or {}).get('action', '')}")
    wb = _words(f"{b.title} {b.action or ''}")
    if len(wa) < 3 or len(wb) < 3:
        return False
    return len(wa & wb) / min(len(wa), len(wb)) >= SAME_STORY


def _grounded(text: str | None, said: list[str]) -> str | None:
    """The STAR part if the candidate's answers back it, else None (a gap)."""
    if not text or not text.strip():
        return None
    text = " ".join(text.split())
    if grounding_problems([Sentence(text=text)], said) != [""]:
        return None
    return text


def _competency_names(session: Session) -> list[str]:
    rubric = (session.rubric_json or {}).get("criteria", [])
    role = [c["name"] for c in rubric if c.get("kind", "role") == "role"]
    return role + CORE_COMPETENCIES


def extract(user_id: int, session: Session, threads: list, scores: dict) -> list[Story]:
    """Add or merge the stories from one finished session.

    `threads` are reports.Thread items; `scores` maps a thread's root question id to
    its evaluation score (a story's strength).
    """
    plan = session.plan_json or {}
    sections = {s["name"]: s for s in plan.get("sections", [])}
    answers, by_answer = [], {}
    for t in threads:
        if (sections.get(t.root.section) or {}).get("module") == "roleplay":
            continue  # role-play replies aren't past experiences
        for q in t.asked:
            a = t.answers.get(q.id)
            if a is None:
                continue
            answers.append(
                {
                    "answer_id": a.id,
                    "question": (q.asked_text or q.text)[:300],
                    "answer": a.transcript,
                }
            )
            by_answer[a.id] = (a.transcript, t.root.id)
    if sum(len(a["answer"].split()) for a in answers) < MIN_WORDS:
        return []

    existing = db.session.scalars(db.select(Story).filter_by(user_id=user_id)).all()
    out = chat_json(
        user_id,
        render(
            "story_extract",
            role=plan.get("role_title") or "the role",
            answers=answers,
            existing=[
                {
                    "id": s.id,
                    "title": s.title,
                    "what_happened": ((s.star_json or {}).get("action") or "")[:200],
                }
                for s in existing
            ],
            competencies=_competency_names(session),
        ),
        StoriesOut,
        SYSTEM,
        max_tokens=1500,
        temperature=0,
    )

    saved = []
    mine = {s.id: s for s in existing}
    for found in out.stories:
        ids = [i for i in dict.fromkeys(found.answer_ids) if i in by_answer]
        if not ids:
            continue
        said = [by_answer[i][0] for i in ids]
        star = {p: _grounded(getattr(found, p), said) for p in PARTS}
        if not star["action"] or HYPOTHETICAL_RE.search(star["action"]):
            continue  # no real action of theirs: not a story
        roots = {by_answer[i][1] for i in ids}
        strength = [scores[r] for r in roots if scores.get(r) is not None]
        strength = round(sum(strength) / len(strength), 2) if strength else None
        comps = list(dict.fromkeys(c.strip() for c in found.competencies if c.strip()))[
            :4
        ]

        twin = mine.get(found.same_as) or next(
            (s for s in mine.values() if _same_story(s, found)), None
        )
        if twin is not None:
            _merge(twin, found.title, star, comps, ids, strength)
            saved.append(twin)
            continue
        story = Story(
            user_id=user_id,
            title=found.title.strip()[:255],
            star_json=star,
            competencies_json=comps,
            source_answer_ids_json=ids,
            strength=strength,
        )
        db.session.add(story)
        db.session.flush()
        mine[story.id] = story
        saved.append(story)
    db.session.commit()
    return saved


def _merge(story: Story, title, star, comps, ids, strength) -> None:
    """Same experience again: keep the stronger telling (unless the user edited it)."""
    stronger = strength is not None and (
        story.strength is None or strength > story.strength
    )
    if stronger and not story.user_edited:
        story.title = title.strip()[:255]
        story.star_json = star
    values = [x for x in (story.strength, strength) if x is not None]
    story.strength = max(values) if values else None
    known = {c.lower() for c in story.competencies_json or []}
    story.competencies_json = (story.competencies_json or []) + [
        c for c in comps if c.lower() not in known
    ]
    story.source_answer_ids_json = list(
        dict.fromkeys((story.source_answer_ids_json or []) + ids)
    )
    story.updated_at = utcnow()


# ---- reading the bank -------------------------------------------------------


def story_dict(story: Story) -> dict:
    star = story.star_json or {}
    rows = db.session.execute(
        db.select(Answer.id, Question.asked_text, Question.text, Session)
        .join(Question, Answer.question_id == Question.id)
        .join(Session, Question.session_id == Session.id)
        .where(Answer.id.in_(story.source_answer_ids_json or []))
    ).all()
    return {
        "id": story.id,
        "title": story.title,
        "star": {p: star.get(p) for p in PARTS},
        "missing": [p for p in PARTS if not star.get(p)],
        "competencies": story.competencies_json or [],
        "strength": story.strength,
        "user_edited": story.user_edited,
        "sources": [
            {
                "session_id": s.id,
                "role": (s.plan_json or {}).get("role_title") or "Interview",
                "question": asked or text,
                "date": (s.started_at or s.created_at).date().isoformat(),
            }
            for _, asked, text, s in rows
        ],
        "created_at": story.created_at.isoformat() + "Z",
        "updated_at": story.updated_at.isoformat() + "Z" if story.updated_at else None,
    }


def _matches(name: str, story: Story) -> bool:
    want = _words(name)
    for c in story.competencies_json or []:
        if _words(c) & want:
            return True
    return False


def coverage(user_id: int, stories: list[Story]) -> dict:
    """Which competencies have stories (core ones plus the latest job's), and gaps."""
    latest = db.session.scalars(
        db.select(Session)
        .filter_by(user_id=user_id)
        .where(Session.rubric_json.is_not(None))
        .order_by(Session.created_at.desc())
    ).first()
    job = (
        [
            c["name"]
            for c in (latest.rubric_json or {}).get("criteria", [])
            if c.get("kind", "role") == "role"
        ]
        if latest
        else []
    )
    names = list(dict.fromkeys(job + CORE_COMPETENCIES))
    rows = [
        {
            "competency": n,
            "core": n in CORE_COMPETENCIES,
            "stories": [s.id for s in stories if _matches(n, s)],
        }
        for n in names
    ]
    return {
        "rows": rows,
        "gaps": [r["competency"] for r in rows if not r["stories"]],
        "job": (latest.plan_json or {}).get("role_title") if latest else None,
    }


def suggest(user_id: int, jd_id: int) -> list[dict]:
    """Stories that fit a job description's competencies (no Fire call)."""
    analysis = db.session.scalar(
        db.select(JdAnalysis)
        .filter_by(document_id=jd_id)
        .where(JdAnalysis.competencies_json.is_not(None))
        .order_by(JdAnalysis.id.desc())
    )
    if analysis is None:
        return []
    wanted = [c["name"] for c in analysis.competencies_json or []]
    out = []
    for story in db.session.scalars(db.select(Story).filter_by(user_id=user_id)):
        fits = [w for w in wanted if _matches(w, story)]
        if fits:
            out.append(
                {
                    "id": story.id,
                    "title": story.title,
                    "fits": fits,
                    "strength": story.strength,
                }
            )
    return sorted(out, key=lambda s: (-len(s["fits"]), -(s["strength"] or 0)))[:5]
