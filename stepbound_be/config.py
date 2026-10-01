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

    INGEST_RATE_LIMIT = os.environ.get("INGEST_RATE_LIMIT", "60/minute;600/hour")
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
