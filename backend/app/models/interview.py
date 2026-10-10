from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
    # SET NULL: a deleted (or auto-expired) document must not take the history with it.
    resume_id: Mapped[int | None] = fk(
        "documents.id", nullable=True, ondelete="SET NULL"
    )
    jd_id: Mapped[int | None] = fk("documents.id", nullable=True, ondelete="SET NULL")
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
    # The small-talk opener ("How's your day going?"): asked first, never scored.
    is_icebreaker: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    # "Do you have any questions for me?" at the end (and "Anything else?"): the
    # candidate's questions to the interviewer. Never scored.
    is_candidate_qa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    # Set for follow-ups the interviewer asks about a planned question.
    follow_up_of_id: Mapped[int | None] = fk("questions.id", nullable=True)
    # When and how the interviewer actually asked it (null = not asked yet).
    asked_at: Mapped[datetime | None] = mapped_column(DateTime)
    asked_text: Mapped[str | None] = mapped_column(Text)
    # asked_text split by speaker for the interviewer's voice:
    # [{"who": "interviewer" | "character", "text": ...}].
    asked_segments: Mapped[list[Any] | None] = mapped_column(JSON)


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
    # "voice" (transcribed clip) or "text" (typed); pace analytics need voice.
    input_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="text", server_default="text"
    )
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
    # Per-criterion comments, weak moments, STAR check and tips from the scorer.
    feedback_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = created_at_column()


REPORT_STATUSES = ("generating", "ready", "failed")


class Report(db.Model):
    """One report per session, built question by question after the interview."""

    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("session_id", name="uq_reports_session"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = fk("sessions.id")
    overall_score: Mapped[float | None] = mapped_column(Float)
    verdict: Mapped[str | None] = mapped_column(String(60))
    verdict_reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="generating", server_default="generating"
    )
    # When the current generation run started; a stale run may be restarted.
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    top_takeaways_json: Mapped[list[Any] | None] = mapped_column(JSON)
    # 2–3 practice drills for the weakest areas.
    exercises_json: Mapped[list[Any] | None] = mapped_column(JSON)
    analytics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Public share link; set to null to revoke.
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = created_at_column()
