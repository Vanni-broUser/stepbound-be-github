"""What is stored. No table holds an IP address, a name, an e-mail or the
install id a phone knows: players are known by an HMAC of it (see
anonymize.py)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .extensions import db


class Player(db.Model):
    """One installation of the game, pseudonymous."""

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # HMAC-SHA256 of the install id, hex.
    player_hash: Mapped[str] = mapped_column(String(64), unique=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    platform: Mapped[str | None] = mapped_column(String(32))
    app_version: Mapped[str | None] = mapped_column(String(64))
    os_version: Mapped[str | None] = mapped_column(String(128))
    device_model: Mapped[str | None] = mapped_column(String(128))


class GameEvent(db.Model):
    """Something a player did, as the game told it: a level started or
    completed, a zombie killed, a death."""

    __tablename__ = "game_events"

    # Made by the phone: a batch sent twice is stored once.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    type: Mapped[str] = mapped_column(String(48))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    app_version: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index("ix_game_events_type_occurred_at", "type", "occurred_at"),
        Index("ix_game_events_occurred_at", "occurred_at"),
    )


class ErrorReport(db.Model):
    """An error the game could not handle, with the report the phone wrote."""

    __tablename__ = "error_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Reports of the same bug share it (see fingerprint.py).
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(128))
    summary: Mapped[str] = mapped_column(String(500))
    app_version: Mapped[str | None] = mapped_column(String(64))
    commit: Mapped[str | None] = mapped_column(String(64))
    platform: Mapped[str | None] = mapped_column(String(32))
    os_version: Mapped[str | None] = mapped_column(String(128))
    device_model: Mapped[str | None] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)

    __table_args__ = (Index("ix_error_reports_occurred_at", "occurred_at"),)
