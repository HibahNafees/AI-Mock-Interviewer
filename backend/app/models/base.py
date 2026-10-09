from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime, default=utcnow, nullable=False)


def fk(target: str, nullable: bool = False, ondelete: str = "CASCADE") -> Mapped[int]:
    """Integer foreign key that cascades deletes ("Delete my data" in one click)."""
    return mapped_column(
        Integer,
        ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
        index=True,
    )
