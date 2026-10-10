"""Résumé gap analysis: one Fire call per résumé + job pair (cached).

A "covered" requirement must quote the résumé; an unverifiable quote downgrades
it to "partial" so the app never claims more than the résumé shows.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

from ..extensions import db
from ..models import Document, GapAnalysis
from .llm import chat_json, render
from .scoring import SYSTEM

MAX_CHARS = 6000


class Requirement(BaseModel):
    requirement: str = Field(min_length=1, max_length=200)
    status: Literal["covered", "partial", "missing"]
    evidence: str | None = Field(default=None, max_length=400)
    likely_question: str | None = Field(default=None, max_length=400)


class GapsOut(BaseModel):
    summary: str = Field(min_length=1, max_length=600)
    requirements: list[Requirement] = Field(min_length=1, max_length=12)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9%$+#./]+", " ", text.lower()).split())


def _verified(r: Requirement, resume_norm: str) -> dict:
    quote = r.evidence.strip() if r.evidence else None
    if quote and (len(_norm(quote).split()) < 2 or _norm(quote) not in resume_norm):
        quote = None  # not really in the résumé
    status = r.status
    if status == "covered" and quote is None:
        status = "partial"  # can't show it from the résumé's own words
    if status == "missing":
        quote = None
    return {
        "requirement": r.requirement.strip(),
        "status": status,
        "evidence": quote,
        "likely_question": (r.likely_question or "").strip() or None,
    }


def analyze(user_id: int, resume: Document, jd: Document) -> dict:
    cached = db.session.scalar(
        db.select(GapAnalysis).filter_by(resume_id=resume.id, jd_id=jd.id)
    )
    if cached is not None:
        return cached.result_json
    out = chat_json(
        user_id,
        render(
            "gap_analysis",
            jd=jd.raw_text[:MAX_CHARS],
            resume=resume.raw_text[:MAX_CHARS],
        ),
        GapsOut,
        SYSTEM,
        max_tokens=1500,
        temperature=0,
    )
    resume_norm = _norm(resume.raw_text)
    reqs = [_verified(r, resume_norm) for r in out.requirements][:10]
    order = {"missing": 0, "partial": 1, "covered": 2}
    reqs.sort(key=lambda r: order[r["status"]])
    result = {
        "summary": out.summary.strip(),
        "requirements": reqs,
        "counts": {k: sum(1 for r in reqs if r["status"] == k) for k in order},
    }
    db.session.add(
        GapAnalysis(
            user_id=user_id, resume_id=resume.id, jd_id=jd.id, result_json=result
        )
    )
    db.session.commit()
    return result
