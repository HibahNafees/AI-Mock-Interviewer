"""Score one question (main answer + follow-ups) and write its stronger version.

One Fire chat call per question covers scores, missing points, weak moments, STAR
and the rewrite. The weighted score is computed here, not by the model, and so is
the check that the rewrite only uses facts the candidate gave (one repair call if
it doesn't; sentences that still aren't grounded are dropped).
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

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
WORD_RE = re.compile(r"[a-z0-9]+")
DIGITS_RE = re.compile(r"\d+")
PLACEHOLDER_RE = re.compile(r"\[[^\]]*\]")
SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")
# A rewrite sentence must share at least this share of its content words with the
# résumé + answers. Calibrated on live gpt-4o-mini rewrites: invented sentences
# ("I also collaborated closely with product teams…") scored 0–0.35, grounded
# ones 0.5+.
MIN_OVERLAP = 0.5
STOPWORDS = frozenset(
    """a an the and or but so to of in on at for with by from as is was were be been
    being it its this that these those i me my we our us you your they them their he
    she his her which who what when where how why than then there here also just very
    more most some any all each both into onto over under about after before while
    during not no only own same such too can could would should will shall may might
    must do does did done have has had having make made get got one way well really
    able""".split()
)
FALLBACK_REWRITE = (
    "[Answer the question with one specific example from your experience: "
    "the situation, what you did, and the result.]"
)


class CriterionScore(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    score: int | None = Field(default=None, ge=1, le=5)  # None: not tested here
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


class Sentence(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    source: str | None = Field(default=None, max_length=1000)


class RewriteOut(BaseModel):
    stronger_version: list[Sentence] = Field(min_length=1, max_length=25)


class ScoreOut(BaseModel):
    criteria: list[CriterionScore] = Field(min_length=1, max_length=12)
    summary: str = Field(min_length=1, max_length=600)
    weak_moments: list[WeakMoment] = Field(default_factory=list, max_length=5)
    missing_points: list[MissingPoint] = Field(default_factory=list, max_length=8)
    star: Star | None = None
    stronger_version: list[Sentence] = Field(min_length=1, max_length=25)
    changes: list[Change] = Field(default_factory=list, max_length=8)
    tips: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def some_criterion_scored(self) -> "ScoreOut":
        if all(c.score is None for c in self.criteria):
            raise ValueError("score at least one criterion")
        return self


def _norm(text: str) -> str:
    return SPACE_RE.sub(" ", text).strip().lower()


def _stem(word: str) -> str:
    return word[:5]


def _content_words(text: str) -> list[str]:
    words = WORD_RE.findall(PLACEHOLDER_RE.sub(" ", text).lower())
    return [w for w in words if len(w) > 2 and w not in STOPWORDS]


def split_sentences(items: list[Sentence]) -> list[Sentence]:
    """The model sometimes returns a paragraph as one item: check it sentence by sentence."""
    return [
        Sentence(text=part, source=item.source)
        for item in items
        for part in SENTENCE_END_RE.split(item.text.strip())
        if part.strip()
    ]


def grounding_problems(sentences: list[Sentence], sources: list[str]) -> list[str]:
    """One message per sentence that isn't backed by the résumé or answers ("" if ok)."""
    corpus_words = WORD_RE.findall(" ".join(sources).lower())
    corpus = " " + " ".join(corpus_words) + " "
    stems = {_stem(w) for w in corpus_words}
    digits = set(DIGITS_RE.findall(" ".join(sources)))
    problems = []
    for s in sentences:
        has_placeholder = bool(PLACEHOLDER_RE.search(s.text))
        quote = " ".join(WORD_RE.findall((s.source or "").lower()))
        content = _content_words(s.text)
        novel = sum(_stem(w) not in stems for w in content)
        # A single linking word ("That led to [the result]") is fine.
        unsupported = novel >= 2 and novel / len(content) > 1 - MIN_OVERLAP
        new_numbers = set(DIGITS_RE.findall(PLACEHOLDER_RE.sub(" ", s.text))) - digits
        if quote and f" {quote} " not in corpus:
            problems.append("its source is not copied from the résumé or answers")
        elif not quote and not has_placeholder:
            problems.append("it has no source and no [placeholder]")
        elif new_numbers:
            problems.append(
                f"it uses numbers the candidate never gave ({', '.join(sorted(new_numbers))})"
            )
        elif unsupported:
            problems.append("it adds details that aren't in its source")
        else:
            problems.append("")
    return problems


def _join(sentences: list[Sentence]) -> str:
    return " ".join(SPACE_RE.sub(" ", s.text).strip() for s in sentences).strip()


def grounded_rewrite(
    user_id: int,
    sentences: list[Sentence],
    sources: list[str],
    question: str,
    resume: str,
    answers: list[str],
    words: int,
) -> str:
    """Join the rewrite, after one repair call if any sentence isn't grounded."""
    sentences = split_sentences(sentences)
    problems = grounding_problems(sentences, sources)
    if any(problems):
        numbered = [f"Sentence {i}: {p}." for i, p in enumerate(problems, start=1) if p]
        prompt = render(
            "rewrite_repair",
            question=question,
            resume=resume,
            answers=answers,
            sentences=[s.model_dump() for s in sentences],
            problems="\n".join(numbered),
            target_words=str(words),
        )
        sentences = chat_json(
            user_id, prompt, RewriteOut, SYSTEM, max_tokens=1200, temperature=0.2
        ).stronger_version
        sentences = split_sentences(sentences)
        problems = grounding_problems(sentences, sources)
    kept = [s for s, p in zip(sentences, problems) if not p]
    return _join(kept) or FALLBACK_REWRITE


def weighted_score(
    scores: list[CriterionScore], rubric: dict | None
) -> tuple[float, list[dict]]:
    """Weighted 1–5 score over the rubric criteria the model scored.

    Criteria the question doesn't test (score None) are left out entirely.
    """
    scores = [s for s in scores if s.score is not None]
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
    resume_text = resume.raw_text[:MAX_RESUME_CHARS] if resume else ""
    words = target_words(budget_sec)
    prompt = render(
        "score",
        role=(session.plan_json or {}).get("role_title") or "the role",
        difficulty=session.difficulty or "mid",
        module=section_module(session, section).replace("_", " "),
        rubric=[
            {k: c.get(k, "") for k in ("name", "description", "strong_answer")}
            for c in (session.rubric_json or {}).get("criteria", [])
        ],
        resume=resume_text or "(not available)",
        exchange=exchange,
        target_words=str(words),
    )
    out = chat_json(user_id, prompt, ScoreOut, SYSTEM, max_tokens=2000, temperature=0.3)
    score, rows = weighted_score(out.criteria, session.rubric_json)
    answers = [e["candidate"] for e in exchange]
    stronger = grounded_rewrite(
        user_id,
        out.stronger_version,
        [resume_text, *answers],
        exchange[0]["interviewer"],
        resume_text,
        answers,
        words,
    )

    said = _norm(" ".join(e["candidate"] for e in exchange))
    weak = [w.model_dump() for w in out.weak_moments if _norm(w.quote) in said][:3]
    evaluation = Evaluation(
        answer_id=answer_id,
        score=score,
        rubric_scores_json={"criteria": rows},
        missing_points_json=[m.model_dump() for m in out.missing_points],
        stronger_version=stronger,
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
