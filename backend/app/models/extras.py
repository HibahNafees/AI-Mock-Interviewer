from datetime import datetime
from typing import Any

from sqlalchemy import JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .base import created_at_column, fk


class GapAnalysis(db.Model):
    """Résumé vs job description: what's covered, partly covered, missing (cached)."""

    __tablename__ = "gap_analyses"
    __table_args__ = (UniqueConstraint("resume_id", "jd_id", name="uq_gap_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = fk("users.id")
    resume_id: Mapped[int] = fk("documents.id")
    jd_id: Mapped[int] = fk("documents.id")
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class CompanyResearch(db.Model):
    """What a company's public page says, summarized once per site (cached)."""

    __tablename__ = "company_research"

    id: Mapped[int] = mapped_column(primary_key=True)
    url_key: Mapped[str] = mapped_column(db.String(64), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(db.String(500), nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
