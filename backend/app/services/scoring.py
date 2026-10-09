"""Score one question (main answer + follow-ups) and write its stronger version.

One Fire chat call per question covers scores, missing points, weak moments, STAR
and the rewrite. The weighted score is computed here, not by the model, and so is
the check that the rewrite only uses facts the candidate gave (one repair call if
it doesn't; sentences that still aren't grounded are dropped).
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, model_validator

from .. import modules
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
WORD_RE = re.compile(r"[a-z]+|\d+")
DIGITS_RE = re.compile(r"\d+")
PLACEHOLDER_RE = re.compile(r"\[[^\]]*\]")
SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")
# Clauses are checked too, so one invented add-on ("…, ensuring they were optimized
# for performance") can't hide behind a well-grounded start.
# "I'd use a token bucket" is a plan, not experience (live check, Phase 5).
HYPOTHETICAL_RE = re.compile(
    r"\b(?:i|we)(?:'|\u2019)d\b|\b(?:i|we) (?:would|might|could|will)\b"
    r"|\b(?:i|we)(?:'|\u2019)ll\b",
    re.IGNORECASE,
)
SOURCE_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]?")
# A stronger version doesn't hedge: "I'm not sure about that one; I'd look at…" keeps
# only the point (live check, T-24).
HEDGE_RE = re.compile(
    r"\bi(?:(?:'|\u2019)?m| am) not (?:sure|certain)\b[^,;:.!?]*(?:[,;:.!?]+|$)\s*(?:but\s+)?"
    r"|\bi (?:don(?:'|\u2019)?t|do not) (?:know|remember)\b[^,;:.!?]*(?:[,;:.!?]+|$)\s*(?:but\s+)?",
    re.IGNORECASE,
)
# Impact claims a rewrite must not add (T-29: "…which significantly improved user
# engagement" when the candidate never said so): intensifiers, and "improved X"
# outcomes, unless the candidate's own words make the same claim.
INTENSIFIER_RE = re.compile(
    r"\b(?:significantly|greatly|dramatically|substantially|considerably|massively|"
    r"hugely|vastly|tremendously|drastically)\b",
    re.IGNORECASE,
)
OUTCOME_RE = re.compile(
    r"\b(?:improv|increas|boost|rais|enhanc|grew|grow|drove|driv)\w*\s+(?:\w+\s+){0,2}?"
    r"(engagement|satisfaction|retention|conversion|morale|revenue|sales|productivity|"
    r"efficiency|adoption|usage)\b",
    re.IGNORECASE,
)
CLAUSE_RE = re.compile(r"[,;:\u2014]|\s(?:which|while|ensuring|allowing|so that)\s")
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
# Units and framing words a faithful rewrite adds ("300ms" → "300 milliseconds",
# "to address this, I…") without adding a fact.
NEUTRAL = frozenset(
    """second seconds milliseconds minute minutes hour hours day days week weeks month
    months year years percent million millions thousand billion address addressed
    issue issues cut reduce reduced reducing result resulted example""".split()
)
# Words every interview question uses; they don't make a résumé line relevant.
QUESTION_WORDS = frozenset(
    """tell walk describe share time times approach specific example examples
    experience challenge challenges faced face ensure successful success role roles
    project projects work worked process handle handled think explain""".split()
)
PAST_VERB_RE = re.compile(
    r"^(?:\w+ed|built|wrote|led|ran|made|grew|taught|won|set|drove|took|kept|"
    r"shipped|began|chose|did|got|held|lost|met|paid|put|read|saw|sold|spent|"
    r"stood|told|thought|understood)$",
    re.IGNORECASE,
)
FALLBACK_STEPS = (
    "[Describe one specific time: the situation, what you did, and the result.]"
)
FALLBACK_REWRITE = (
    "[Answer the question with one specific example from your experience: "
    "the situation, what you did, and the result.]"
)


RETRY_RULE = (
    "- This answer is a retry: score EVERY criterion in the rubric above from 1 to 5 "
    "(no nulls), so it can be compared with the first attempt.\n"
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
    def some_criterion_scored(self, info: ValidationInfo) -> "ScoreOut":
        if all(c.score is None for c in self.criteria):
            raise ValueError("score at least one criterion")
        # A retry must be scored on the criteria its first attempt was (T-29).
        required = (info.context or {}).get("required") or []
        scored = {_norm(c.name) for c in self.criteria if c.score is not None}
        missing = [n for n in required if _norm(n) not in scored]
        if missing:
            raise ValueError(
                f"score every listed criterion; missing: {', '.join(missing)}"
            )
        return self


def _norm(text: str) -> str:
    return SPACE_RE.sub(" ", text).strip().lower()


def _stem(word: str) -> str:
    return word[:5]


def _content_words(text: str) -> list[str]:
    words = WORD_RE.findall(PLACEHOLDER_RE.sub(" ", text).lower())
    return [w for w in words if len(w) > 2 and w not in STOPWORDS | NEUTRAL]


def _adds_details(text: str, stems: set[str]) -> bool:
    """Most of the sentence (or of one of its clauses) isn't in the sources."""
    for part in [text, *CLAUSE_RE.split(text)]:
        content = _content_words(part)
        novel = sum(_stem(w) not in stems for w in content)
        # A single linking word ("That led to [the result]") is fine.
        if novel >= 2 and novel / len(content) > 1 - MIN_OVERLAP:
            return True
    return False


def _without_hedge(text: str) -> str:
    text = HEDGE_RE.sub("", text).strip()
    return text[:1].upper() + text[1:]


def split_sentences(items: list[Sentence]) -> list[Sentence]:
    """The model sometimes returns a paragraph as one item: check it sentence by
    sentence. Hedges ("I'm not sure, but…") are cut; a sentence that was only a
    hedge is dropped.
    """
    return [
        Sentence(text=_without_hedge(part), source=item.source)
        for item in items
        for part in SENTENCE_END_RE.split(item.text.strip())
        if _without_hedge(part)
    ]


def _factual(sources: list[str]) -> str:
    """The sources without hypothetical sentences ("I'd…", "I would…")."""
    return " ".join(
        part
        for text in sources
        for part in SOURCE_SENTENCE_RE.findall(text)
        if not HYPOTHETICAL_RE.search(part)
    )


def grounding_problems(sentences: list[Sentence], sources: list[str]) -> list[str]:
    """One message per sentence that isn't backed by the résumé or answers ("" if ok).

    The model's cited `source` is only a prompt for it to stay grounded (it often
    leaves it out for faithful sentences); the check is on the sentence itself. A
    sentence stated as fact must be backed by facts, not only by what the candidate
    said they would do.
    """
    stems = {_stem(w) for w in WORD_RE.findall(" ".join(sources).lower())}
    factual = {_stem(w) for w in WORD_RE.findall(_factual(sources).lower())}
    digits = set(DIGITS_RE.findall(" ".join(sources)))
    said = " ".join(sources)
    intensifiers = {w.lower() for w in INTENSIFIER_RE.findall(said)}
    outcomes = {o.lower() for o in OUTCOME_RE.findall(said)}
    problems = []
    for s in sentences:
        text = PLACEHOLDER_RE.sub(" ", s.text)
        new_numbers = set(DIGITS_RE.findall(text)) - digits
        new_impact = {w.lower() for w in INTENSIFIER_RE.findall(text)} - intensifiers
        if not PLACEHOLDER_RE.search(s.text):
            # "That improved engagement by [add the %]" asks for the real result.
            new_impact |= {o.lower() for o in OUTCOME_RE.findall(text)} - outcomes
        if new_numbers:
            problems.append(
                f"it uses numbers the candidate never gave ({', '.join(sorted(new_numbers))})"
            )
        elif new_impact:
            problems.append(
                f"it claims an impact the candidate never stated ({', '.join(sorted(new_impact))})"
            )
        elif _adds_details(s.text, stems):
            problems.append("it adds details the candidate never gave")
        elif not HYPOTHETICAL_RE.search(s.text) and _adds_details(s.text, factual):
            problems.append(
                "it presents what the candidate said they would do as something they did"
            )
        else:
            problems.append("")
    return problems


def _resume_facts(resume: str) -> list[tuple[str, str]]:
    """(employer, fact) pairs from résumé lines like "Acme (2021–now): Built X; did Y."."""
    facts = []
    for line in resume.splitlines():
        employer, _, rest = line.partition(":")
        if not rest.strip():
            employer, rest = "", line
        employer = employer.split("(")[0].strip()
        for fact in re.split(r";|\.\s", rest):
            fact = fact.strip().rstrip(".")
            if len(fact.split()) >= 2:
                facts.append((employer, fact))
    return facts


def resume_fallback(question: str, resume: str) -> str:
    """Rewrite skeleton for an answer with nothing usable: the résumé line that fits
    the question (no Fire call), plus a placeholder for the story."""
    asked = {_stem(w) for w in _content_words(question) if w not in QUESTION_WORDS}
    best, best_hits = None, 0
    for employer, fact in _resume_facts(resume):
        hits = len(asked & {_stem(w) for w in _content_words(fact)})
        if hits > best_hits:
            best, best_hits = (employer, fact), hits
    if best is None:
        return FALLBACK_REWRITE
    employer, fact = best
    first = fact.split()[0]
    if PAST_VERB_RE.match(first):
        where = f"At {employer}, I" if employer else "I"
        return f"{where} {fact[0].lower()}{fact[1:]}. {FALLBACK_STEPS}"
    return f'[Build this from your résumé: "{fact}".] {FALLBACK_STEPS}'


# Openers that point back at the previous sentence. When that sentence was dropped
# (or there is none), linking words are cut and a "this/that/it" subject becomes a
# placeholder, so the rewrite never refers to something the user can't see.
LINK_OPENER_RE = re.compile(
    r"^(?:to address (?:this|that|these|it)|as a result|because of this|"
    r"for (?:instance|example)|additionally|also|however|in addition|then|so|"
    r"this way|that way|initially)\b[,:]?\s*",
    re.IGNORECASE,
)
ACTION_VERBS = (
    r"(?:\w+ed|cut|let|made|led|took|kept|gave|brought|meant|got|helped|saved|"
    r"enabled|ensured|allowed|caused)\b"
)
# "This change cut…" → "[What you changed] cut…"; "These keys ensured…" → "The keys…".
SUBJECT_OPENER_RE = re.compile(
    rf"^(?:(?P<det>this|that|these|those)(?: (?P<noun>[a-z]+))?|it) (?={ACTION_VERBS})",
    re.IGNORECASE,
)
VAGUE_NOUNS = frozenset(
    """change changes move fix approach step steps decision work effort improvement
    improvements solution update optimization optimizations""".split()
)
DANGLING_SUBJECT = "[What you changed] "
# The model sometimes knows a phrase was misheard and flags it anyway (live check,
# T-19): a weak moment that blames transcription isn't the candidate's fault.
MISHEARING_RE = re.compile(
    r"transcri|mishear|misheard|speech[- ]recognition|speech[- ]to[- ]text",
    re.IGNORECASE,
)


def _subject(match: re.Match) -> str:
    noun = match["noun"]
    if noun and noun.lower() not in VAGUE_NOUNS:
        return f"The {noun} "
    return DANGLING_SUBJECT


def _detach(text: str) -> str:
    """Make a sentence stand on its own once the sentence before it is gone."""
    text = LINK_OPENER_RE.sub("", text, count=1)
    text = SUBJECT_OPENER_RE.sub(_subject, text, count=1)
    return text[:1].upper() + text[1:] if text and text[0] != "[" else text


def _keep(sentences: list[Sentence], problems: list[str]) -> list[Sentence]:
    """Grounded sentences, detached from any dropped sentence they followed."""
    kept: list[Sentence] = []
    previous_kept = False
    for s, problem in zip(sentences, problems):
        if problem:
            previous_kept = False
            continue
        text = s.text if previous_kept else _detach(s.text)
        kept.append(Sentence(text=text, source=s.source))
        previous_kept = True
    return kept


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
    changes: list["Change"],
) -> tuple[str, list["Change"]]:
    """The rewrite (after one repair call if any sentence isn't grounded) and the
    "what changed" list, kept only when the scorer's rewrite passed unchanged:
    otherwise it would describe text the user never sees.
    """
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
        repaired = chat_json(
            user_id, prompt, RewriteOut, SYSTEM, max_tokens=1200, temperature=0.2
        )
        sentences = split_sentences(repaired.stronger_version)
        changes = []
        problems = grounding_problems(sentences, sources)
    kept = _keep(sentences, problems)
    if not any(WORD_RE.search(PLACEHOLDER_RE.sub(" ", s.text).lower()) for s in kept):
        # Nothing but bare placeholders left: start from the résumé instead.
        return resume_fallback(question, resume), []
    return _join(kept), changes if len(kept) == len(sentences) else []


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


def section_plan(session: Session, section: str) -> dict:
    for s in (session.plan_json or {}).get("sections", []):
        if s["name"] == section:
            return s
    return {}


def section_module(session: Session, section: str) -> str:
    return section_plan(session, section).get("module", modules.DEFAULT)


def evaluate(
    user_id: int,
    session: Session,
    answer_id: int,
    section: str,
    budget_sec: int | None,
    exchange: list[dict],
    clips: list[Clip],
    question: str | None = None,
    criteria: list[str] | None = None,
) -> Evaluation:
    """One Fire chat call → a saved Evaluation for `answer_id`.

    `exchange` is [{"interviewer": ..., "candidate": ...}], main question first.
    `criteria` (for "Try again") limits scoring to the criteria the first attempt
    was scored on, all of them required, so before and after compare like with like.
    """
    resume = db.session.get(Document, session.resume_id) if session.resume_id else None
    resume_text = resume.raw_text[:MAX_RESUME_CHARS] if resume else ""
    words = target_words(budget_sec)
    plan = section_plan(session, section)
    scenario = plan.get("scenario") if plan.get("module") == "roleplay" else None
    rubric = session.rubric_json or {}
    if criteria:
        wanted = {_norm(n) for n in criteria}
        rubric = {
            **rubric,
            "criteria": [
                c for c in rubric.get("criteria", []) if _norm(c["name"]) in wanted
            ],
        }
    prompt = render(
        "score",
        role=(session.plan_json or {}).get("role_title") or "the role",
        difficulty=session.difficulty or "mid",
        module=modules.MODULES.get(
            module := section_module(session, section),
            modules.MODULES[modules.DEFAULT],
        ).label,
        module_guidance=modules.guidance(module, "score"),
        scenario=scenario or "none",
        rubric=[
            {k: c.get(k, "") for k in ("name", "description", "strong_answer")}
            for c in rubric.get("criteria", [])
        ],
        criteria_rule=RETRY_RULE if criteria else "",
        resume=resume_text or "(not available)",
        exchange=exchange,
        target_words=str(words),
    )
    # Temperature 0: the same answer should get the same score (T-29).
    out = chat_json(
        user_id,
        prompt,
        ScoreOut,
        SYSTEM,
        max_tokens=2000,
        temperature=0,
        context={"required": criteria or []},
    )
    score, rows = weighted_score(out.criteria, rubric)
    answers = [e["candidate"] for e in exchange]
    stronger, changes = grounded_rewrite(
        user_id,
        out.stronger_version,
        # In a role-play the reply may refer to what the character said.
        [resume_text, *answers]
        + (
            [e["interviewer"] for e in exchange] + list(scenario.values())
            if scenario
            else []
        ),
        question or exchange[0]["interviewer"],
        resume_text,
        answers,
        words,
        out.changes,
    )

    said = _norm(" ".join(e["candidate"] for e in exchange))
    weak = [
        w.model_dump()
        for w in out.weak_moments
        if _norm(w.quote) in said and not MISHEARING_RE.search(w.why)
    ][:3]
    evaluation = Evaluation(
        answer_id=answer_id,
        score=score,
        rubric_scores_json={"criteria": rows},
        missing_points_json=[m.model_dump() for m in out.missing_points],
        stronger_version=stronger,
        changes_json=[c.model_dump() for c in changes],
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
