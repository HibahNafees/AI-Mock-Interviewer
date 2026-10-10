from datetime import date as date_type
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .base import created_at_column, fk


class JdDecode(db.Model):
    """A decoded job description, cached by text hash and shareable by token.

    The JD text itself isn't kept: only its hash and the interpretation.
    """

    __tablename__ = "jd_decodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    share_token: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    user_id: Mapped[int | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    # Salted hash of the requester's IP, for the anonymous daily cap only.
    ip_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = created_at_column()


class SavedDecode(db.Model):
    """A decode in a signed-in user's list, to come back to (or delete)."""

    __tablename__ = "saved_decodes"
    __table_args__ = (UniqueConstraint("user_id", "decode_id", name="uq_saved_decode"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = fk("users.id")
    decode_id: Mapped[int] = fk("jd_decodes.id")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # Last time the user decoded (or re-decoded) this posting.
    saved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class AnonSpend(db.Model):
    """Fire spend from signed-out use (the decoder), counted in the monthly budget."""

    __tablename__ = "anon_spend"

    date: Mapped[date_type] = mapped_column(Date, primary_key=True)
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fire_spend_usd: Mapped[float] = mapped_column(
        Numeric(10, 6), nullable=False, default=0
    )
