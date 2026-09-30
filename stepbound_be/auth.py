"""The two keys: the app's, on ingest, and the admin's, on reading."""

from __future__ import annotations

import hmac
from functools import wraps

from flask import abort, current_app, request


def _matches(given: str | None, expected: str) -> bool:
    return bool(expected) and given is not None and hmac.compare_digest(
        given.encode("utf-8"), expected.encode("utf-8")
    )


def require_ingest_key(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not _matches(request.headers.get("X-Stepbound-Key"), current_app.config["INGEST_KEY"]):
            abort(401)
        return view(*args, **kwargs)

    return wrapper


def require_admin(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else None
        if not _matches(token, current_app.config["ADMIN_TOKEN"]):
            abort(401)
        return view(*args, **kwargs)

    return wrapper
