"""JD analysis, question plan and rubric (Fire chat), plus plan bookkeeping."""

import re
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from .. import modules
from ..extensions import db
from ..models import Document, JdAnalysis, Question, Session, User
from . import panel
from .llm import chat_json, render

ALL_MODULES = tuple(modules.MODULES)
MIXED = "mixed"
# "Roleplay: Objection Handling" next to "Objection Handling" (live check, T-21).
ROLEPLAY_PREFIX_RE = re.compile(
    r"^\s*role[- ]?play\s*[:\-\u2013\u2014]\s*", re.IGNORECASE
)
# The character speaking as the candidate's side ("Hi, I'm Priya from ShopNest, how
# can I assist you?"), live check T-23.
HELPER_LINE_RE = re.compile(
    r"\bhow (?:can|may) i (?:help|assist)\b|\bthanks? (?:you )?for (?:calling|contacting)\b",
    re.IGNORECASE,
)

SYSTEM = (
    "You are an expert interview coach who designs realistic, fair job interviews. "
    "Reply with a single JSON object only, no prose and no code fences."
)


# ---- LLM output schemas ---------------------------------------------------


class Competency(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class JdAnalysisOut(BaseModel):
    role_title: str = Field(min_length=1, max_length=200)
    field: str = Field(min_length=1, max_length=120)
    seniority: str = Field(min_length=1, max_length=60)
    competencies: list[Competency] = Field(min_length=1, max_length=12)
    formats: list[str] = Field(min_length=1)
    licensed_field: bool = False

    @field_validator("formats")
    @classmethod
    def known_formats(cls, v: list[str]) -> list[str]:
        kept = [f for f in dict.fromkeys(v) if f in ALL_MODULES]
        return kept or ["behavioral", "resume_deepdive"]


class Scenario(BaseModel):
    """A role-play: who the interviewer plays, where, and what the candidate must do."""

    character: str = Field(min_length=1, max_length=300)
    setting: str = Field(default="", max_length=400)
    goal: str = Field(min_length=1, max_length=300)
    # Instructions only the character sees (e.g. how far a recruiter may move);
    # never shown to the candidate before the report.
    private: str = Field(default="", max_length=1200)


# Most questions in one section (10 coding problems fit in one, T-85).
MAX_QUESTIONS = 10


class PlanSectionOut(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    module: str
    minutes: int = Field(ge=1, le=60)
    questions: list[str] = Field(default_factory=list, max_length=MAX_QUESTIONS)
    scenario: Scenario | None = None

    @field_validator("questions", mode="before")
    @classmethod
    def only_text(cls, v: object) -> object:
        # gpt-4o-mini sometimes puts the role-play scenario object in "questions".
        if isinstance(v, list):
            return [q for q in v if isinstance(q, str)]
        return v

    @field_validator("module")
    @classmethod
    def available_module(cls, v: str) -> str:
        return v if modules.known(v) else modules.DEFAULT

    @model_validator(mode="after")
    def roleplay_needs_scenario(self) -> "PlanSectionOut":
        if self.module == "roleplay" and self.scenario is None:
            raise ValueError("A role-play section needs a scenario")
        if self.module != "roleplay":
            self.scenario = None
        elif not self.questions:
            self.questions = [neutral_opener(self.scenario)]
        if not self.questions:
            raise ValueError("Each section needs at least one question")
        return self


def neutral_opener(scenario: Scenario) -> str:
    """An opening line for a character whose planned one is missing or unusable."""
    name = re.split(r"[,(\u2014-]", scenario.character)[0].strip()
    if name[:1].isupper() and not re.match(r"(?:A|An|The)\b", name):
        return f"Hi, this is {name}. So, what did you want to talk about?"
    return "Hi. So, what did you want to talk about?"


def candidate_names(resume: str, user_name: str = "") -> set[str]:
    """First names that identify the candidate: the résumé's first word and the account name."""
    first_line = resume.strip().split("\n", 1)[0] if resume.strip() else ""
    words = [
        first_line.split()[0] if first_line.split() else "",
        *user_name.split()[:1],
    ]
    return {w.strip(",.").lower() for w in words if w[:1].isupper() and w.isalpha()}


def fix_reversed_opener(section: PlanSectionOut, names: set[str]) -> None:
    """Swap an opening line spoken as the candidate's side (introducing themselves by
    the candidate's name, offering help) for a neutral one."""
    if section.module != "roleplay" or section.scenario is None:
        return
    line = section.questions[0]
    said_by_candidate = HELPER_LINE_RE.search(line) or any(
        re.search(
            rf"\b(?:this is|i(?:'|\u2019)m|i am|my name is) {re.escape(n)}\b",
            line,
            re.IGNORECASE,
        )
        for n in names
    )
    if said_by_candidate:
        section.questions[0] = neutral_opener(section.scenario)


STOPWORDS = frozenset(
    "a an and are as at be by can could do does for from given how i in into is it "
    "its me of on or should that the this to tell us was we what when where which "
    "who why will with would write you your design implement build function".split()
)


def _words(text: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[a-z0-9]+", text.lower())
        if len(w) > 2 and w not in STOPWORDS
    }


def similar(a: str, b: str, threshold: float = 0.6) -> bool:
    """Two questions ask the same thing: most of their content words match."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return a.strip().lower() == b.strip().lower()
    return len(wa & wb) / min(len(wa), len(wb)) >= threshold


# How many earlier hands-on questions the plan is told to avoid (T-90).
RECENT_SESSIONS = 10
RECENT_HANDS_ON = 15


def recent_hands_on(user_id: int) -> list[str]:
    """Coding problems and design questions from the user's recent sessions,
    newest first, so a new plan doesn't hand out the same ones again."""
    sessions = db.session.scalars(
        db.select(Session)
        .filter_by(user_id=user_id)
        .order_by(Session.id.desc())
        .limit(RECENT_SESSIONS)
    ).all()
    out: list[str] = []
    for session in sessions:
        names = {
            s["name"]
            for s in (session.plan_json or {}).get("sections", [])
            if s.get("module") in HANDS_ON_MIN
        }
        if not names:
            continue
        rows = db.session.scalars(
            db.select(Question.text)
            .filter_by(session_id=session.id, is_bonus=False, follow_up_of_id=None)
            .where(Question.section.in_(names))
            .order_by(Question.order_no)
        ).all()
        out += [t for t in rows if not any(similar(t, o) for o in out)]
    return out[:RECENT_HANDS_ON]


class BonusOut(BaseModel):
    section: str
    text: str = Field(min_length=1)


class PlanOut(BaseModel):
    sections: list[PlanSectionOut] = Field(min_length=1, max_length=6)
    reserve: list[BonusOut] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def hands_on_as_asked(self, info: ValidationInfo) -> "PlanOut":
        """The coding problems and design question the candidate asked for (T-65)."""
        ctx = info.context or {}
        for module, wanted in (
            ("coding", ctx.get("coding")),
            ("system_design", ctx.get("system_design")),
        ):
            if wanted is None:
                continue
            got = sum(len(s.questions) for s in self.sections if s.module == module)
            if got != wanted:
                raise ValueError(
                    f'use exactly {wanted} question(s) in "{module}" sections (got {got})'
                )
        # Repeated coding problems or design questions (T-90). Only for generated
        # plans (they pass a context); the candidate's own edits aren't second-guessed.
        seen: list[str] = []
        for s in self.sections if info.context is not None else []:
            if s.module not in HANDS_ON_MIN:
                continue
            for q in s.questions:
                if any(similar(q, other) for other in seen):
                    raise ValueError(
                        f'every "{s.module}" question must be a different problem; '
                        f"this one repeats an earlier one: {q[:80]}"
                    )
                seen.append(q)
        return self


class Criterion(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["role", "universal"]
    weight: float = Field(gt=0, le=1)
    description: str = Field(min_length=1, max_length=500)
    strong_answer: str = Field(default="", max_length=500)


class RubricOut(BaseModel):
    criteria: list[Criterion] = Field(min_length=3, max_length=10)


# ---- Fire calls -------------------------------------------------------------


def analyze_jd(user_id: int, jd: Document) -> JdAnalysis:
    """Role analysis for a job description, cached per document."""
    existing = db.session.scalar(
        db.select(JdAnalysis)
        .filter_by(document_id=jd.id)
        .where(JdAnalysis.competencies_json.is_not(None))
        .order_by(JdAnalysis.id.desc())
    )
    if existing:
        return existing
    out = chat_json(
        user_id, render("jd_analysis", jd=jd.raw_text), JdAnalysisOut, SYSTEM
    )
    analysis = JdAnalysis(
        document_id=jd.id,
        field=out.field,
        seniority=out.seniority,
        competencies_json=[c.model_dump() for c in out.competencies],
        formats_json=out.formats,
        decoder_json={
            "role_title": out.role_title,
            "licensed_field": out.licensed_field,
        },
    )
    db.session.add(analysis)
    db.session.commit()
    return analysis


def analysis_summary(analysis: JdAnalysis) -> dict:
    extra = analysis.decoder_json or {}
    return {
        "role_title": extra.get("role_title", ""),
        "field": analysis.field,
        "seniority": analysis.seniority,
        "competencies": analysis.competencies_json or [],
        "formats": analysis.formats_json or [],
        "licensed_field": bool(extra.get("licensed_field")),
    }


# Software roles always get the coding round and the whiteboard (T-62: the JD
# analysis left them out for a "Software Developer" posting).
SOFTWARE_RE = re.compile(
    r"software|developer|programm|web|backend|back-end|frontend|front-end|full[- ]?stack"
    r"|devops|cloud|data (?:engineer|scien)|machine learning|\bml\b|computer|mobile",
    re.IGNORECASE,
)


def offered_modules(analysis: JdAnalysis) -> list[str]:
    """Modules that fit this job."""
    summary = analysis_summary(analysis)
    fit = [f for f in summary["formats"] if modules.known(f)]
    # A software field is enough on its own: the analysis sometimes leaves
    # "technical" out, e.g. for an intern posting (T-89). A software word in the
    # title alone (a software sales rep) still needs "technical".
    software_field = SOFTWARE_RE.search(summary["field"])
    if software_field or (
        "technical" in fit
        and SOFTWARE_RE.search(f"{summary['field']} {summary['role_title']}")
    ):
        fit += [m for m in ("technical", "coding", "system_design") if m not in fit]
    return fit or ["behavioral", "resume_deepdive"]


MINUTES_PER_PROBLEM = 8
# Time per hands-on question when the plan decides how many (T-81)...
HANDS_ON_MIN = {"coding": MINUTES_PER_PROBLEM, "system_design": 10}
# ...and the least each gets when the candidate picks the count (1–10 each, T-85).
HANDS_ON_FLOOR = {"coding": 4, "system_design": 5}
MAX_HANDS_ON = 10
# Minutes a mixed loop keeps for its other sections.
OTHER_MIN = 2


def hands_on_limit(duration_min: int, only: bool = False) -> int:
    """How many coding problems fit when the plan decides (about 8 minutes each, at
    most 3). `only`: the whole interview is coding, so at least one."""
    spare = duration_min if only else duration_min - OTHER_MIN
    return max(1 if only else 0, min(3, spare // MINUTES_PER_PROBLEM))


def fit_counts(
    duration_min: int, coding: int | None, design: int | None, only: bool = False
) -> tuple[int | None, int | None]:
    """Trim the candidate's chosen counts to what fits at the floor minutes
    (coding first). The setup page blocks counts that don't fit; this is the
    server-side guard."""
    spare = duration_min if only else duration_min - OTHER_MIN
    if coding is not None:
        coding = min(coding, MAX_HANDS_ON, spare // HANDS_ON_FLOOR["coding"])
        if only:
            coding = max(coding, 1)
        spare -= coding * HANDS_ON_FLOOR["coding"]
    if design is not None:
        design = max(
            0, min(design, MAX_HANDS_ON, spare // HANDS_ON_FLOOR["system_design"])
        )
    return coding, design


def fit_hands_on(
    allowed: list[str], duration_min: int, reserved: dict[str, int] | None = None
) -> list[str]:
    """Drop the coding round and the whiteboard from a mixed loop when the
    interview is too short for them (a 5-minute plan once gave each 2 minutes).
    `reserved`: modules whose count the candidate chose, with the minutes they
    take; they stay (if the count isn't 0) and the plan-decided ones get the rest.
    Coding is kept before system design."""
    reserved = reserved or {}
    spare = duration_min - OTHER_MIN - sum(reserved.values())
    out = []
    for m in allowed:
        need = HANDS_ON_MIN.get(m)
        if m in reserved:
            if reserved[m]:
                out.append(m)
        elif need is None:
            out.append(m)
        elif spare >= need:
            out.append(m)
            spare -= need
    return out or allowed


def section_need(section, per_question: dict[str, int] | None = None) -> int:
    """Least minutes a section needs (0 for ordinary sections): its per-question
    minimum times its questions."""
    return (per_question or HANDS_ON_MIN).get(section.module, 0) * len(
        section.questions
    )


def enforce_hands_on(
    sections: list, duration_min: int, per_question: dict[str, int] | None = None
) -> list:
    """Give coding and design sections their minimum minutes, taken from the other
    sections' spare time (each keeps at least 1, or its own minimum). Hands-on
    questions that still don't fit are dropped; a section left with none is removed."""

    def need(s) -> int:
        return section_need(s, per_question)

    for s in sections:
        while s.minutes < need(s):
            donors = [d for d in sections if d is not s and d.minutes > max(1, need(d))]
            if donors:
                donor = max(donors, key=lambda d: d.minutes - need(d))
                donor.minutes -= 1
                s.minutes += 1
            elif len(s.questions) > 1:
                s.questions = s.questions[:-1]
            else:
                break
    kept = [s for s in sections if s.minutes >= need(s)]
    if kept and len(kept) < len(sections):
        return normalize_minutes(kept, duration_min)
    return sections


def build_plan(
    user_id: int,
    resume: Document,
    analysis: JdAnalysis,
    duration_min: int,
    difficulty: str,
    focus: str = MIXED,
    coding: int | None = None,
    system_design: int | None = None,
) -> PlanOut:
    """`coding` / `system_design`: how many of each the candidate asked for, 0–10
    (None = the plan decides)."""
    summary = analysis_summary(analysis)
    allowed = offered_modules(analysis) if focus == MIXED else [focus]
    if "coding" not in allowed:
        coding = None
    if "system_design" not in allowed or focus != MIXED:
        system_design = None
    coding, system_design = fit_counts(
        duration_min, coding, system_design, only=focus != MIXED
    )
    chosen = {
        m: n
        for m, n in (("coding", coding), ("system_design", system_design))
        if n is not None
    }
    # Chosen counts get the floor minutes; plan-decided ones the full time.
    per_question = {
        m: HANDS_ON_FLOOR[m] if m in chosen else HANDS_ON_MIN[m] for m in HANDS_ON_MIN
    }
    if focus == MIXED:
        allowed = fit_hands_on(
            allowed, duration_min, {m: n * HANDS_ON_FLOOR[m] for m, n in chosen.items()}
        )
    rules, ctx = [], {}
    for module, n in chosen.items():
        what = "coding problem" if module == "coding" else "system design question"
        ctx[module] = n
        rules.append(
            f'Use exactly {n} {what}(s): each is one question in a section with module "{module}".'
            if n
            else f'Don\'t use the "{module}" module.'
        )
    avoid = recent_hands_on(user_id) if any(m in HANDS_ON_MIN for m in allowed) else []
    if avoid:
        rules.append(
            "The candidate already practised these problems; give different ones "
            "(a different task, not a reworded one):\n"
            + "\n".join(f"- {q}" for q in avoid)
        )
    if any(m in HANDS_ON_MIN for m in allowed):
        rules.append(
            "Every coding problem and design question in this plan must be a different "
            "problem that tests a different skill."
        )
    focus_rule = (
        "Mix the modules to fit the role: a full interview loop."
        if focus == MIXED
        else f'The candidate chose to practise only "{modules.MODULES[focus].label}": '
        f'every section uses the "{focus}" module.'
    )
    prompt = render(
        "plan",
        role=summary,
        resume=resume.raw_text,
        duration_min=str(duration_min),
        difficulty=difficulty,
        modules=allowed,
        module_guidance=modules.plan_guidance(allowed),
        focus_rule=focus_rule,
        max_sections=str(section_limit(duration_min)),
        question_count=str(question_target(duration_min)),
        hands_on="\n".join(rules) or "",
    )
    # Warmer than the default so the same résumé and job don't always get the same
    # problems (T-90).
    plan = chat_json(
        user_id,
        prompt,
        PlanOut,
        SYSTEM,
        max_tokens=2000,
        temperature=0.7,
        context=ctx,
    )
    plan.reserve = [
        b
        for b in plan.reserve
        if not any(similar(b.text, q) for sec in plan.sections for q in sec.questions)
    ]
    user = db.session.get(User, user_id)
    names = candidate_names(resume.raw_text, user.name if user else "")
    for section in plan.sections:
        if section.module not in allowed:
            section.module = allowed[0]
            if section.module == "roleplay" and section.scenario is None:
                section.module = modules.DEFAULT
        fix_reversed_opener(section, names)
    plan.sections = normalize_minutes(plan.sections, duration_min)
    if focus == MIXED:
        plan.sections = enforce_hands_on(plan.sections, duration_min, per_question)
    return plan


def build_rubric(
    user_id: int, analysis: JdAnalysis, difficulty: str, focus: str = MIXED
) -> RubricOut:
    prompt = render(
        "rubric",
        role=analysis_summary(analysis),
        difficulty=difficulty,
        focus=(
            "a full mixed interview"
            if focus == MIXED
            else f"{modules.MODULES[focus].label} questions only"
        ),
    )
    rubric = chat_json(user_id, prompt, RubricOut, SYSTEM)
    rubric.criteria = dedupe_criteria(rubric.criteria)
    for c, w in zip(rubric.criteria, share_weights(rubric.criteria)):
        c.weight = round(w, 3)
    return rubric


# Communication (Structure, Clarity, Relevance) is 30% of every score. The model
# gave it 0.05 each, so a rambling answer barely lost points (T-74).
UNIVERSAL_SHARE = 0.3


def share_weights(criteria: list) -> list[float]:
    """Weights summing to 1: role criteria share 70% in proportion to their own
    weights, universal ones split 30% equally (all of it if only one kind)."""

    def get(c, key):
        return c[key] if isinstance(c, dict) else getattr(c, key)

    role = [get(c, "weight") or 0 for c in criteria if get(c, "kind") == "role"]
    n_uni = sum(1 for c in criteria if get(c, "kind") != "role")
    uni_share = UNIVERSAL_SHARE if role and n_uni else (1.0 if n_uni else 0.0)
    role_total = sum(role) or 1
    out = []
    for c in criteria:
        if get(c, "kind") == "role":
            w = get(c, "weight") or 0
            out.append(
                (1 - uni_share) * (w / role_total if sum(role) else 1 / len(role))
            )
        else:
            out.append(uni_share / n_uni)
    return out


def dedupe_criteria(criteria: list[Criterion]) -> list[Criterion]:
    """Drop "Role-play:" prefixes and merge criteria that then share a name."""
    kept: dict[str, Criterion] = {}
    for c in criteria:
        c.name = ROLEPLAY_PREFIX_RE.sub("", c.name).strip() or c.name
        key = c.name.lower()
        if key in kept:
            kept[key].weight = min(1.0, kept[key].weight + c.weight)
        else:
            kept[key] = c
    return list(kept.values())


# ---- Plan bookkeeping (no Fire calls) -------------------------------------


def section_limit(duration_min: int) -> int:
    return 2 if duration_min <= 10 else 3 if duration_min <= 30 else 4


def question_target(duration_min: int) -> int:
    """Roughly one main question per 4 minutes (follow-ups fill the rest)."""
    return max(2, round(duration_min / 4))


def normalize_minutes(sections: list, duration_min: int) -> list:
    """Scale section minutes so they are whole, at least 1, and sum to the duration."""
    sections = sections[:duration_min]
    total = sum(s.minutes for s in sections) or 1
    for s in sections:
        s.minutes = max(1, round(s.minutes * duration_min / total))
    diff = duration_min - sum(s.minutes for s in sections)
    ordered = sorted(sections, key=lambda s: s.minutes, reverse=True)
    i = 0
    while diff != 0:
        s = ordered[i % len(ordered)]
        step = 1 if diff > 0 else -1
        if s.minutes + step >= 1:
            s.minutes += step
            diff -= step
        i += 1
    return sections


WHY_US = "Why this company"
WHY_US_MINUTES = 2


def add_why_us(plan: PlanOut, questions: list[str]) -> None:
    """A short company-fit section at the end, its minutes taken from the longest
    section so the total stays the same (company research)."""
    if not questions:
        return
    # Never from a coding or design section: they need their full time.
    spare = [
        s
        for s in plan.sections
        if s.minutes - WHY_US_MINUTES >= max(1, section_need(s))
    ]
    if not spare:
        return
    longest = max(spare, key=lambda s: s.minutes - section_need(s))
    if longest.minutes <= WHY_US_MINUTES:
        return  # too short an interview to spare the time
    longest.minutes -= WHY_US_MINUTES
    plan.sections.append(
        PlanSectionOut(
            name=WHY_US,
            module="behavioral",
            minutes=WHY_US_MINUTES,
            questions=questions[:2],
        )
    )


def save_plan(session: Session, plan: PlanOut, role_title: str = "") -> None:
    """Replace the session's question rows and plan_json with `plan`."""
    db.session.execute(db.delete(Question).filter_by(session_id=session.id))
    order = 0
    for s in plan.sections:
        budget = round(s.minutes * 60 / len(s.questions))
        for text in s.questions:
            order += 1
            db.session.add(
                Question(
                    session_id=session.id,
                    section=s.name,
                    order_no=order,
                    text=text.strip(),
                    budget_sec=budget,
                    is_bonus=False,
                )
            )
    names = {s.name for s in plan.sections}
    for b in plan.reserve:
        order += 1
        section = b.section if b.section in names else plan.sections[-1].name
        db.session.add(
            Question(
                session_id=session.id,
                section=section,
                order_no=order,
                text=b.text.strip(),
                budget_sec=180,
                is_bonus=True,
            )
        )
    previous = session.plan_json or {}
    hidden = {
        s["name"]: (s.get("scenario") or {}).get("private", "")
        for s in previous.get("sections", [])
    }
    for s in plan.sections:
        # An edited plan keeps the character's private instructions.
        if s.scenario is not None and not s.scenario.private:
            s.scenario.private = hidden.get(s.name, "")
    session.plan_json = {
        **previous,
        "role_title": role_title or previous.get("role_title", ""),
        "sections": [
            {
                "name": s.name,
                "module": s.module,
                "minutes": s.minutes,
                "scenario": (
                    s.scenario.model_dump(
                        exclude={"private"} if not s.scenario.private else None
                    )
                    if s.scenario
                    else None
                ),
            }
            for s in plan.sections
        ],
    }
    if session.mode == "panel":
        panel.assign(session)
    db.session.commit()


def plan_view(session: Session) -> dict:
    """The editable plan as the setup page shows it."""
    rows = db.session.scalars(
        db.select(Question)
        .filter_by(session_id=session.id, follow_up_of_id=None)
        .order_by(Question.order_no)
    ).all()
    sections = []
    for s in (session.plan_json or {}).get("sections", []):
        scenario = s.get("scenario")
        sections.append(
            {
                **s,
                "scenario": (
                    {k: v for k, v in scenario.items() if k != "private"}
                    if scenario
                    else None
                ),
                "questions": [
                    q.text for q in rows if q.section == s["name"] and not q.is_bonus
                ],
            }
        )
    reserve = [{"section": q.section, "text": q.text} for q in rows if q.is_bonus]
    return {"sections": sections, "reserve": reserve}
