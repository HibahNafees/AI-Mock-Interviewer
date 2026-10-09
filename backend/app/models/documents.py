from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .base import created_at_column, fk


class Document(db.Model):
    """Parsed résumé or job description. Original files are deleted after parsing."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = fk("users.id")
    kind: Mapped[str] = mapped_column(
        Enum("resume", "job_description", name="document_kind"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(255))
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Null means the user saved it; otherwise it auto-deletes at this time.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = created_at_column()


class JdAnalysis(db.Model):
    """Role analysis of a job description; shared by setup and the decoder."""

    __tablename__ = "jd_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = fk("documents.id")
    field: Mapped[str | None] = mapped_column(String(120))
    seniority: Mapped[str | None] = mapped_column(String(60))
    competencies_json: Mapped[list[Any] | None] = mapped_column(JSON)
    formats_json: Mapped[list[Any] | None] = mapped_column(JSON)
    decoder_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = created_at_column()
