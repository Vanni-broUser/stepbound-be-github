"""POST /v1/ingest: what a phone had waiting in its outbox.

Sending is at-least-once: a phone that loses the connection before the
answer sends the same batch again. Events and reports carry the id the
phone gave them, and one already stored is skipped, so the answer is 200
either way and the phone empties its outbox."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert

from .auth import require_ingest_key
from .anonymize import player_hash
from .extensions import db, limiter
from .fingerprint import fingerprint
from .models import ErrorReport, GameEvent, Player
from .validation import Batch, Invalid, Limits, parse_batch

bp = Blueprint("ingest", __name__)


def _install_id_key() -> str:
    """The phone a request comes from, for its own rate limit: the install
    id in the body (a request without one is refused anyway)."""
    body = request.get_json(silent=True)
    install_id = body.get("installId") if isinstance(body, dict) else None
    return f"install:{install_id}" if isinstance(install_id, str) else "install:-"


def _limited(view):
    """Both limits: the address's, generous, and the phone's own."""
    view = limiter.limit(
        lambda: current_app.config["PLAYER_RATE_LIMIT"], key_func=_install_id_key
    )(view)
    return limiter.limit(lambda: current_app.config["INGEST_RATE_LIMIT"])(view)


def _limits() -> Limits:
    config = current_app.config
    return Limits(
        max_events=config["MAX_EVENTS_PER_BATCH"],
        max_reports=config["MAX_REPORTS_PER_BATCH"],
        max_report_bytes=config["MAX_REPORT_BYTES"],
        max_event_data_bytes=config["MAX_EVENT_DATA_BYTES"],
    )


def _upsert_player(batch: Batch, now: datetime) -> int:
    app = batch.app
    values = {
        "player_hash": player_hash(batch.install_id, current_app.config["PLAYER_ID_PEPPER"]),
        "first_seen": now,
        "last_seen": now,
        "platform": app.platform,
        "app_version": app.version,
        "os_version": app.os,
        "device_model": app.model,
    }
    statement = insert(Player).values(**values)
    excluded = statement.excluded
    statement = statement.on_conflict_do_update(
        index_elements=[Player.player_hash],
        set_={
            "last_seen": func.greatest(Player.last_seen, excluded.last_seen),
            "platform": func.coalesce(excluded.platform, Player.platform),
            "app_version": func.coalesce(excluded.app_version, Player.app_version),
            "os_version": func.coalesce(excluded.os_version, Player.os_version),
            "device_model": func.coalesce(excluded.device_model, Player.device_model),
        },
    ).returning(Player.id)
    return db.session.execute(statement).scalar_one()


def store(batch: Batch, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    player_id = _upsert_player(batch, now)
    app = batch.app

    stored_events = 0
    if batch.events:
        statement = (
            insert(GameEvent)
            .values(
                [
                    {
                        "id": event.id,
                        "player_id": player_id,
                        "session_id": event.session,
                        "type": event.type,
                        "occurred_at": event.at,
                        "received_at": now,
                        "app_version": app.version,
                        "data": event.data,
                    }
                    for event in batch.events
                ]
            )
            .on_conflict_do_nothing(index_elements=[GameEvent.id])
            .returning(GameEvent.id)
        )
        stored_events = len(db.session.execute(statement).all())

    stored_reports = 0
    if batch.reports:
        statement = (
            insert(ErrorReport)
            .values(
                [
                    {
                        "id": report.id,
                        "player_id": player_id,
                        "occurred_at": report.at,
                        "received_at": now,
                        "fingerprint": fingerprint(report.source, report.summary, report.text),
                        "source": report.source,
                        "summary": report.summary,
                        "app_version": app.version,
                        "commit": app.commit,
                        "platform": app.platform,
                        "os_version": app.os,
                        "device_model": app.model,
                        "body": report.text,
                    }
                    for report in batch.reports
                ]
            )
            .on_conflict_do_nothing(index_elements=[ErrorReport.id])
            .returning(ErrorReport.id)
        )
        stored_reports = len(db.session.execute(statement).all())

    db.session.commit()
    return {
        "events": stored_events,
        "reports": stored_reports,
        "duplicates": len(batch.events) + len(batch.reports) - stored_events - stored_reports,
    }


@bp.post("/v1/ingest")
@_limited
@require_ingest_key
def ingest():
    body = request.get_json(silent=True)
    try:
        batch = parse_batch(body, _limits())
    except Invalid as error:
        return jsonify(error=str(error)), 400
    return jsonify(stored=store(batch)), 200


@bp.post("/v1/forget")
@_limited
@require_ingest_key
def forget():
    """The player turned sending off: everything stored under their install
    id goes (events and reports with it, by cascade)."""
    body = request.get_json(silent=True)
    install_id = body.get("installId") if isinstance(body, dict) else None
    try:
        parse_batch({"installId": install_id}, _limits())
    except Invalid as error:
        return jsonify(error=str(error)), 400
    hashed = player_hash(install_id, current_app.config["PLAYER_ID_PEPPER"])
    removed = db.session.execute(delete(Player).where(Player.player_hash == hashed)).rowcount
    db.session.commit()
    return jsonify(forgotten=bool(removed)), 200
