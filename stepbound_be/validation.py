"""Reads the body of POST /v1/ingest, and says what is wrong with it.

A batch is what the phone had waiting in its outbox:

    {
      "installId": "<random id made by the app>",
      "app": {"version": "0.1.0 (402)", "commit": "abc123", "platform": "android",
              "os": "Android 11 (SDK 30)", "model": "Xiaomi Redmi 9"},
      "events":  [{"id": "<uuid>", "type": "level_completed", "at": "<iso8601>",
                   "session": "<uuid>", "data": {...}}],
      "reports": [{"id": "<uuid>", "at": "<iso8601>", "source": "async",
                   "summary": "...", "text": "<the whole report>"}]
    }

Everything but installId may be missing.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
_INSTALL_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

# Phones with a wrong clock: an event dated outside this window is dated
# when it arrived instead.
_PAST = timedelta(days=120)
_FUTURE = timedelta(days=1)


class Invalid(ValueError):
    pass


@dataclass(frozen=True)
class AppInfo:
    version: str | None = None
    commit: str | None = None
    platform: str | None = None
    os: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class EventIn:
    id: uuid.UUID
    type: str
    at: datetime
    session: uuid.UUID | None
    data: dict


@dataclass(frozen=True)
class ReportIn:
    id: uuid.UUID
    at: datetime
    source: str
    summary: str
    text: str


@dataclass(frozen=True)
class Batch:
    install_id: str
    app: AppInfo
    events: list[EventIn] = field(default_factory=list)
    reports: list[ReportIn] = field(default_factory=list)


@dataclass(frozen=True)
class Limits:
    max_events: int
    max_reports: int
    max_report_bytes: int
    max_event_data_bytes: int


def _text(value: object, name: str, limit: int, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise Invalid(f"{name} is required")
        return None
    if not isinstance(value, str):
        raise Invalid(f"{name} must be a string")
    value = value.strip()
    if required and not value:
        raise Invalid(f"{name} is required")
    return value[:limit] or None


def _uuid(value: object, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise Invalid(f"{name} must be a UUID") from None


def _when(value: object, now: datetime) -> datetime:
    if not isinstance(value, str):
        return now
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return now
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    if not now - _PAST <= at <= now + _FUTURE:
        return now
    return at


def parse_batch(body: object, limits: Limits, now: datetime | None = None) -> Batch:
    now = now or datetime.now(timezone.utc)
    if not isinstance(body, dict):
        raise Invalid("body must be a JSON object")

    install_id = body.get("installId")
    if not isinstance(install_id, str) or not _INSTALL_ID.match(install_id):
        raise Invalid("installId must be 16 to 64 letters, digits, - or _")

    raw_app = body.get("app") or {}
    if not isinstance(raw_app, dict):
        raise Invalid("app must be an object")
    app = AppInfo(
        version=_text(raw_app.get("version"), "app.version", 64),
        commit=_text(raw_app.get("commit"), "app.commit", 64),
        platform=_text(raw_app.get("platform"), "app.platform", 32),
        os=_text(raw_app.get("os"), "app.os", 128),
        model=_text(raw_app.get("model"), "app.model", 128),
    )

    raw_events = body.get("events") or []
    raw_reports = body.get("reports") or []
    if not isinstance(raw_events, list) or not isinstance(raw_reports, list):
        raise Invalid("events and reports must be lists")
    if len(raw_events) > limits.max_events:
        raise Invalid(f"at most {limits.max_events} events per batch")
    if len(raw_reports) > limits.max_reports:
        raise Invalid(f"at most {limits.max_reports} reports per batch")

    events = []
    for index, raw in enumerate(raw_events):
        name = f"events[{index}]"
        if not isinstance(raw, dict):
            raise Invalid(f"{name} must be an object")
        kind = raw.get("type")
        if not isinstance(kind, str) or not _EVENT_TYPE.match(kind):
            raise Invalid(f"{name}.type must be snake_case, at most 48 characters")
        data = raw.get("data") or {}
        if not isinstance(data, dict):
            raise Invalid(f"{name}.data must be an object")
        if len(json.dumps(data, separators=(",", ":"))) > limits.max_event_data_bytes:
            raise Invalid(f"{name}.data is larger than {limits.max_event_data_bytes} bytes")
        session = raw.get("session")
        events.append(
            EventIn(
                id=_uuid(raw.get("id"), f"{name}.id"),
                type=kind,
                at=_when(raw.get("at"), now),
                session=None if session is None else _uuid(session, f"{name}.session"),
                data=data,
            )
        )

    reports = []
    for index, raw in enumerate(raw_reports):
        name = f"reports[{index}]"
        if not isinstance(raw, dict):
            raise Invalid(f"{name} must be an object")
        text = _text(raw.get("text"), f"{name}.text", 10**9, required=True)
        if len(text.encode("utf-8")) > limits.max_report_bytes:
            raise Invalid(f"{name}.text is larger than {limits.max_report_bytes} bytes")
        reports.append(
            ReportIn(
                id=_uuid(raw.get("id"), f"{name}.id"),
                at=_when(raw.get("at"), now),
                source=_text(raw.get("source"), f"{name}.source", 128) or "sconosciuta",
                summary=_text(raw.get("summary"), f"{name}.summary", 500) or "(nessun riassunto)",
                text=text,
            )
        )

    return Batch(install_id=install_id, app=app, events=events, reports=reports)
