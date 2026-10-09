"""JD analysis, question plan and rubric (Fire chat), plus plan bookkeeping."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..extensions import db
from ..models import Document, JdAnalysis, Question, Session
from .llm import chat_json, render

# Text-friendly format modules available before the any-job phase adds the rest.
TEXT_MODULES = (
    "behavioral",
    "resume_deepdive",
    "technical",
    "case",
    "scenario",
    "portfolio",
)
ALL_MODULES = TEXT_MODULES + ("coding", "system_design", "roleplay")

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


class PlanSectionOut(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    module: str
    minutes: int = Field(ge=1, le=60)
    questions: list[str] = Field(min_length=1, max_length=8)

    @field_validator("module")
    @classmethod
    def text_module(cls, v: str) -> str:
        return v if v in TEXT_MODULES else "behavioral"


class BonusOut(BaseModel):
    section: str
    text: str = Field(min_length=1)


class PlanOut(BaseModel):
    sections: list[PlanSectionOut] = Field(min_length=1, max_length=6)
    reserve: list[BonusOut] = Field(default_factory=list, max_length=6)


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


def build_plan(
    user_id: int,
    resume: Document,
    analysis: JdAnalysis,
    duration_min: int,
    difficulty: str,
) -> PlanOut:
    summary = analysis_summary(analysis)
    allowed = [f for f in summary["formats"] if f in TEXT_MODULES] or [
        "behavioral",
        "resume_deepdive",
    ]
    prompt = render(
        "plan",
        role=summary,
        resume=resume.raw_text,
        duration_min=str(duration_min),
        difficulty=difficulty,
        modules=allowed,
        max_sections=str(section_limit(duration_min)),
        question_count=str(question_target(duration_min)),
    )
    plan = chat_json(user_id, prompt, PlanOut, SYSTEM, max_tokens=2000)
    plan.sections = normalize_minutes(plan.sections, duration_min)
    return plan


def build_rubric(user_id: int, analysis: JdAnalysis, difficulty: str) -> RubricOut:
    prompt = render("rubric", role=analysis_summary(analysis), difficulty=difficulty)
    rubric = chat_json(user_id, prompt, RubricOut, SYSTEM)
    total = sum(c.weight for c in rubric.criteria)
    for c in rubric.criteria:
        c.weight = round(c.weight / total, 3)
    return rubric


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
    session.plan_json = {
        **previous,
        "role_title": role_title or previous.get("role_title", ""),
        "sections": [
            {"name": s.name, "module": s.module, "minutes": s.minutes}
            for s in plan.sections
        ],
    }
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
        sections.append(
            {
                **s,
                "questions": [
                    q.text for q in rows if q.section == s["name"] and not q.is_bonus
                ],
            }
        )
    reserve = [{"section": q.section, "text": q.text} for q in rows if q.is_bonus]
    return {"sections": sections, "reserve": reserve}
