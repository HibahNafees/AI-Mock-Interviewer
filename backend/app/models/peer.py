from datetime import datetime

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .base import created_at_column, fk


class PeerRoom(db.Model):
    """Peer practice room; both sides must consent before anyone is heard."""

    __tablename__ = "peer_rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_user_id: Mapped[int] = fk("users.id")
    guest_user_id: Mapped[int | None] = fk("users.id", nullable=True)
    invite_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    consent_host: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_guest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    session_id: Mapped[int | None] = fk("sessions.id", nullable=True)
    created_at: Mapped[datetime] = created_at_column()
