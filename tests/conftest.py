import os

import pytest
from sqlalchemy import text

from stepbound_be import create_app
from stepbound_be.extensions import db, limiter

INGEST_KEY = "test-ingest-key"
ADMIN_TOKEN = "test-admin-token"


@pytest.fixture(scope="session")
def app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": os.environ.get(
                "TEST_DATABASE_URL",
                "postgresql+psycopg://postgres@127.0.0.1:5432/stepbound_test",
            ),
            "INGEST_KEY": INGEST_KEY,
            "PLAYER_ID_PEPPER": "test-pepper",
            "ADMIN_TOKEN": ADMIN_TOKEN,
            "INGEST_RATE_LIMIT": "1000/minute",
            "PLAYER_RATE_LIMIT": "1000/minute",
            "ADMIN_FAILED_AUTH_LIMIT": "1000/minute",
        }
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(autouse=True)
def clean(app):
    yield
    db.session.rollback()
    db.session.execute(text("truncate game_events, error_reports, players restart identity"))
    db.session.commit()
    limiter.reset()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def ingest(client):
    def send(body, key=INGEST_KEY):
        return client.post("/v1/ingest", json=body, headers={"X-Stepbound-Key": key})

    return send


@pytest.fixture
def admin(client):
    def get(path, token=ADMIN_TOKEN):
        return client.get(path, headers={"Authorization": f"Bearer {token}"})

    return get
