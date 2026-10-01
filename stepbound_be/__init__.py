"""stepbound-be: receives what the Stepbound app sends on its own (error
reports and anonymous gameplay events) and answers questions about it."""

from __future__ import annotations

from flask import Flask, jsonify
from sqlalchemy import text
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .extensions import db, limiter, migrate


def create_app(config: type | dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if isinstance(config, dict):
        app.config.update(config)
    elif config is not None:
        app.config.from_object(config)

    for key in ("INGEST_KEY", "PLAYER_ID_PEPPER", "ADMIN_TOKEN"):
        if not app.config.get(key) and not app.testing:
            raise RuntimeError(f"{key} is not set (see .env.example)")

    if app.config["TRUSTED_PROXIES"]:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=app.config["TRUSTED_PROXIES"],
            x_proto=app.config["TRUSTED_PROXIES"],
        )

    db.init_app(app)
    migrate.init_app(app, db, directory=str(_migrations_dir()))
    limiter.init_app(app)

    from . import models  # noqa: F401  (the tables, for Alembic)
    from .cli import register as register_cli
    from .ingest import bp as ingest_bp
    from .stats import bp as stats_bp

    app.register_blueprint(ingest_bp)
    app.register_blueprint(stats_bp)
    register_cli(app)

    @app.get("/healthz")
    def healthz():
        db.session.execute(text("select 1"))
        return jsonify(status="ok")

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        return jsonify(error=error.name.lower()), error.code

    return app


def _migrations_dir():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent / "migrations"
