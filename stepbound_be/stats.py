"""What the data says, for whoever holds ADMIN_TOKEN.

Every endpoint takes ?days=N (default 30, at most 400): only what happened
in the last N days is counted. The event types and their data are the
ones the app sends (see docs/events.md)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, jsonify, request
from sqlalchemy import Float, cast, distinct, func, select

from .auth import require_admin
from .extensions import db
from .models import ErrorReport, GameEvent, Player

bp = Blueprint("stats", __name__, url_prefix="/v1")


def _since() -> datetime:
    try:
        days = int(request.args.get("days", 30))
    except ValueError:
        abort(400)
    days = max(1, min(days, 400))
    return datetime.now(timezone.utc) - timedelta(days=days)


def _field(name: str):
    return GameEvent.data[name].astext


def _number(name: str):
    return cast(_field(name), Float)


def _rows(statement) -> list[dict]:
    return [dict(row._mapping) for row in db.session.execute(statement)]


@bp.get("/stats/overview")
@require_admin
def overview():
    since = _since()
    day = func.date_trunc("day", GameEvent.occurred_at).label("day")
    daily = db.session.execute(
        select(day, func.count(distinct(GameEvent.player_id)).label("players"))
        .where(GameEvent.occurred_at >= since)
        .group_by(day)
        .order_by(day)
    )
    sessions = db.session.execute(
        select(
            func.count().label("sessions"),
            func.avg(_number("seconds")).label("avg_seconds"),
            func.sum(_number("seconds")).label("total_seconds"),
        ).where(GameEvent.type == "session_ended", GameEvent.occurred_at >= since)
    ).one()
    return jsonify(
        players_total=db.session.scalar(select(func.count()).select_from(Player)),
        players_new=db.session.scalar(
            select(func.count()).select_from(Player).where(Player.first_seen >= since)
        ),
        players_active=db.session.scalar(
            select(func.count(distinct(GameEvent.player_id))).where(
                GameEvent.occurred_at >= since
            )
        ),
        daily_active=[
            {"day": row.day.date().isoformat(), "players": row.players} for row in daily
        ],
        sessions=sessions.sessions,
        avg_session_seconds=round(sessions.avg_seconds or 0, 1),
        total_play_hours=round((sessions.total_seconds or 0) / 3600, 1),
        platforms=_rows(
            select(Player.platform, func.count().label("players"))
            .where(Player.last_seen >= since)
            .group_by(Player.platform)
            .order_by(func.count().desc())
        ),
        versions=_rows(
            select(Player.app_version, func.count().label("players"))
            .where(Player.last_seen >= since)
            .group_by(Player.app_version)
            .order_by(func.count().desc())
        ),
    )


@bp.get("/stats/levels")
@require_admin
def levels():
    since = _since()
    level = _field("level").label("level")

    def players(kind: str) -> dict[str, int]:
        return {
            row.level: row.players
            for row in db.session.execute(
                select(level, func.count(distinct(GameEvent.player_id)).label("players"))
                .where(GameEvent.type == kind, GameEvent.occurred_at >= since)
                .group_by(level)
            )
        }

    started = players("level_started")
    completed = players("level_completed")
    averages = {
        row.level: row
        for row in db.session.execute(
            select(
                level,
                func.count().label("completions"),
                func.avg(_number("zombiesKilled")).label("zombies_killed"),
                func.avg(_number("zombiesTotal")).label("zombies_total"),
                func.avg(_number("backpacks")).label("backpacks"),
                func.avg(_number("memories")).label("memories"),
                func.avg(_number("steps")).label("steps"),
                func.avg(_number("playSeconds")).label("play_seconds"),
            )
            .where(GameEvent.type == "level_completed", GameEvent.occurred_at >= since)
            .group_by(level)
        )
    }
    deaths = players("player_died")
    result = []
    for name in sorted(set(started) | set(completed)):
        row = averages.get(name)
        begun = started.get(name, 0)
        done = completed.get(name, 0)

        def avg(value):
            return None if value is None else round(value, 1)

        result.append(
            {
                "level": name,
                "players_started": begun,
                "players_completed": done,
                "completion_rate": round(done / begun, 3) if begun else None,
                "players_died": deaths.get(name, 0),
                "completions": row.completions if row else 0,
                "avg_zombies_killed": avg(row.zombies_killed) if row else None,
                "avg_zombies_total": avg(row.zombies_total) if row else None,
                "avg_backpacks": avg(row.backpacks) if row else None,
                "avg_memories": avg(row.memories) if row else None,
                "avg_steps": avg(row.steps) if row else None,
                "avg_play_minutes": avg(row.play_seconds / 60)
                if row and row.play_seconds is not None
                else None,
            }
        )
    return jsonify(levels=result)


@bp.get("/stats/zombies")
@require_admin
def zombies():
    since = _since()
    kind = _field("kind").label("kind")
    killer = _field("killer").label("killer")
    return jsonify(
        killed=_rows(
            select(
                kind,
                func.count().label("kills"),
                func.count(distinct(GameEvent.player_id)).label("players"),
            )
            .where(GameEvent.type == "zombie_killed", GameEvent.occurred_at >= since)
            .group_by(kind)
            .order_by(func.count().desc())
        ),
        killed_player=_rows(
            select(killer, func.count().label("deaths"))
            .where(GameEvent.type == "player_died", GameEvent.occurred_at >= since)
            .group_by(killer)
            .order_by(func.count().desc())
        ),
    )


@bp.get("/stats/places")
@require_admin
def places():
    """Where players go and where they die: the places reached by the most
    players first, so the one where many stop shows as a drop."""
    since = _since()
    level = _field("level").label("level")
    place = _field("place").label("place")
    reached = _rows(
        select(level, place, func.count(distinct(GameEvent.player_id)).label("players"))
        .where(GameEvent.type == "place_entered", GameEvent.occurred_at >= since)
        .group_by(level, place)
        .order_by(level, func.count(distinct(GameEvent.player_id)).desc())
    )
    deaths = _rows(
        select(level, place, func.count().label("deaths"))
        .where(GameEvent.type == "player_died", GameEvent.occurred_at >= since)
        .group_by(level, place)
        .order_by(func.count().desc())
    )
    return jsonify(reached=reached, deaths=deaths)


@bp.get("/stats/events")
@require_admin
def event_counts():
    since = _since()
    return jsonify(
        events=_rows(
            select(
                GameEvent.type,
                func.count().label("events"),
                func.count(distinct(GameEvent.player_id)).label("players"),
            )
            .where(GameEvent.occurred_at >= since)
            .group_by(GameEvent.type)
            .order_by(func.count().desc())
        )
    )


@bp.get("/errors")
@require_admin
def errors():
    """The bugs, most frequent first: reports grouped by fingerprint."""
    since = _since()
    latest = (
        select(
            ErrorReport.fingerprint,
            ErrorReport.id,
            ErrorReport.summary,
            ErrorReport.source,
            ErrorReport.app_version,
            func.row_number()
            .over(partition_by=ErrorReport.fingerprint, order_by=ErrorReport.occurred_at.desc())
            .label("rank"),
        )
        .where(ErrorReport.occurred_at >= since)
        .subquery()
    )
    groups = (
        select(
            ErrorReport.fingerprint,
            func.count().label("reports"),
            func.count(distinct(ErrorReport.player_id)).label("players"),
            func.min(ErrorReport.occurred_at).label("first_seen"),
            func.max(ErrorReport.occurred_at).label("last_seen"),
        )
        .where(ErrorReport.occurred_at >= since)
        .group_by(ErrorReport.fingerprint)
        .subquery()
    )
    rows = db.session.execute(
        select(groups, latest.c.id, latest.c.summary, latest.c.source, latest.c.app_version)
        .join(latest, latest.c.fingerprint == groups.c.fingerprint)
        .where(latest.c.rank == 1)
        .order_by(groups.c.reports.desc(), groups.c.last_seen.desc())
    )
    return jsonify(
        errors=[
            {
                "fingerprint": row.fingerprint,
                "reports": row.reports,
                "players": row.players,
                "first_seen": row.first_seen.isoformat(),
                "last_seen": row.last_seen.isoformat(),
                "latest_id": str(row.id),
                "summary": row.summary,
                "source": row.source,
                "latest_version": row.app_version,
            }
            for row in rows
        ]
    )


@bp.get("/errors/<report_id>")
@require_admin
def error_detail(report_id: str):
    try:
        key = uuid.UUID(report_id)
    except ValueError:
        abort(404)
    report = db.session.get(ErrorReport, key)
    if report is None:
        abort(404)
    if request.args.get("format") == "text":
        return report.body, 200, {"Content-Type": "text/plain; charset=utf-8"}
    return jsonify(
        id=str(report.id),
        fingerprint=report.fingerprint,
        occurred_at=report.occurred_at.isoformat(),
        received_at=report.received_at.isoformat(),
        source=report.source,
        summary=report.summary,
        app_version=report.app_version,
        commit=report.commit,
        platform=report.platform,
        os_version=report.os_version,
        device_model=report.device_model,
        body=report.body,
    )
