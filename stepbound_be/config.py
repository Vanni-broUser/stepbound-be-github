"""Settings, read from the environment (see .env.example)."""

from __future__ import annotations

import os


def _int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return default if value in (None, "") else int(value)


class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://stepbound:stepbound@localhost:5432/stepbound",
    )
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    INGEST_KEY = os.environ.get("INGEST_KEY", "")
    PLAYER_ID_PEPPER = os.environ.get("PLAYER_ID_PEPPER", "")
    ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

    # Per client address. Generous: on mobile networks thousands of phones
    # can share one address (carrier NAT), and a phone sends only a few
    # batches an hour.
    INGEST_RATE_LIMIT = os.environ.get("INGEST_RATE_LIMIT", "300/minute;5000/hour")
    # Per install id: what one phone may send, whatever its address. A
    # phone over it gets 429 and keeps its outbox for later.
    PLAYER_RATE_LIMIT = os.environ.get("PLAYER_RATE_LIMIT", "20/minute;200/hour")
    # Per client address, counting only wrong admin tokens: someone
    # guessing is stopped, the admin with the right token never is.
    ADMIN_FAILED_AUTH_LIMIT = os.environ.get("ADMIN_FAILED_AUTH_LIMIT", "10/minute;50/day")
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    TRUSTED_PROXIES = _int("TRUSTED_PROXIES", 1)

    # A whole request: the app sends at most a few reports and a few hundred
    # events at a time, far below this.
    MAX_CONTENT_LENGTH = _int("MAX_CONTENT_LENGTH", 1024 * 1024)
    MAX_EVENTS_PER_BATCH = _int("MAX_EVENTS_PER_BATCH", 500)
    MAX_REPORTS_PER_BATCH = _int("MAX_REPORTS_PER_BATCH", 5)
    MAX_REPORT_BYTES = _int("MAX_REPORT_BYTES", 256 * 1024)
    MAX_EVENT_DATA_BYTES = _int("MAX_EVENT_DATA_BYTES", 4 * 1024)

    EVENT_RETENTION_DAYS = _int("EVENT_RETENTION_DAYS", 395)
    REPORT_RETENTION_DAYS = _int("REPORT_RETENTION_DAYS", 180)
