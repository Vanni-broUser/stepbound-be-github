"""flask purge: removes what is older than the retention the privacy policy
promises. Run it once a day (cron, a systemd timer, or the scheduler of the
host)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import click
from flask import Flask, current_app
from sqlalchemy import delete, exists, select

from .extensions import db
from .models import ErrorReport, GameEvent, Player


def purge(now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    config = current_app.config
    events = db.session.execute(
        delete(GameEvent).where(
            GameEvent.occurred_at < now - timedelta(days=config["EVENT_RETENTION_DAYS"])
        )
    ).rowcount
    reports = db.session.execute(
        delete(ErrorReport).where(
            ErrorReport.occurred_at < now - timedelta(days=config["REPORT_RETENTION_DAYS"])
        )
    ).rowcount
    # A player with nothing left, and not seen for as long, goes too.
    players = db.session.execute(
        delete(Player).where(
            Player.last_seen < now - timedelta(days=config["EVENT_RETENTION_DAYS"]),
            ~exists(select(GameEvent.id).where(GameEvent.player_id == Player.id)),
            ~exists(select(ErrorReport.id).where(ErrorReport.player_id == Player.id)),
        )
    ).rowcount
    db.session.commit()
    return {"events": events, "reports": reports, "players": players}


def register(app: Flask) -> None:
    @app.cli.command("purge")
    def purge_command():
        """Delete events and reports past their retention."""
        removed = purge()
        click.echo(
            f"removed {removed['events']} events, {removed['reports']} reports, "
            f"{removed['players']} players"
        )
