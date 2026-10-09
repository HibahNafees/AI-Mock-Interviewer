from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .base import created_at_column, fk

SESSION_MODES = (
    "standard",
    "reverse",
    "pressure",
    "panel",
    "negotiation",
    "peer",
    "debrief",
)
SESSION_STATUSES = ("planned", "active", "completed", "abandoned")


class Session(db.Model):
    """One row per interview."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = fk("users.id")
    resume_id: Mapped[int | None] = fk("documents.id", nullable=True)
    jd_id: Mapped[int | None] = fk("documents.id", nullable=True)
    mode: Mapped[str] = mapped_column(
        Enum(*SESSION_MODES, name="session_mode"), nullable=False, default="standard"
    )
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[str | None] = mapped_column(String(30))
    persona: Mapped[str | None] = mapped_column(String(60))
    pressure_level: Mapped[int | None] = mapped_column(Integer)
    plan_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    rubric_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        Enum(*SESSION_STATUSES, name="session_status"),
        nullable=False,
        default="planned",
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = created_at_column()


class Question(db.Model):
    """The question plan for a session."""

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = fk("sessions.id")
    section: Mapped[str] = mapped_column(String(120), nullable=False)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    budget_sec: Mapped[int | None] = mapped_column(Integer)
    is_bonus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Answer(db.Model):
    """Transcript of one answer. Audio is never stored."""

    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = fk("questions.id")
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    started_ms: Mapped[int | None] = mapped_column(Integer)
    ended_ms: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    hints_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = created_at_column()


class Evaluation(db.Model):
    """Score and recommendations for one answer."""

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    answer_id: Mapped[int] = fk("answers.id")
    score: Mapped[float | None] = mapped_column(Float)
    rubric_scores_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    missing_points_json: Mapped[list[Any] | None] = mapped_column(JSON)
    stronger_version: Mapped[str | None] = mapped_column(Text)
    changes_json: Mapped[list[Any] | None] = mapped_column(JSON)
    delivery_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = created_at_column()


class Report(db.Model):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = fk("sessions.id")
    overall_score: Mapped[float | None] = mapped_column(Float)
    verdict: Mapped[str | None] = mapped_column(String(60))
    top_takeaways_json: Mapped[list[Any] | None] = mapped_column(JSON)
    analytics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Public share link; set to null to revoke.
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = created_at_column()
