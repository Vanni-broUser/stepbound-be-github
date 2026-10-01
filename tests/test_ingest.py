import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from stepbound_be.anonymize import player_hash
from stepbound_be.extensions import db
from stepbound_be.models import ErrorReport, GameEvent, Player

INSTALL = "a1b2c3d4e5f60718293a4b5c6d7e8f90"


def event(event_type="level_started", **data):
    return {
        "id": str(uuid.uuid4()),
        "type": event_type,
        "at": datetime.now(timezone.utc).isoformat(),
        "session": str(uuid.uuid4()),
        "data": data,
    }


def report(**overrides):
    body = {
        "id": str(uuid.uuid4()),
        "at": datetime.now(timezone.utc).isoformat(),
        "source": "async",
        "summary": "RangeError (index): Invalid value: Not in inclusive range 0..3: 7",
        "text": "RAPPORTO DI ERRORE DI STEPBOUND\n#0      World.step (package:stepbound/core/world.dart:12:3)\n",
    }
    body.update(overrides)
    return body


APP = {"version": "0.1.0 (402)", "commit": "abc123", "platform": "android", "os": "Android 11", "model": "Xiaomi Redmi 9"}


def test_stores_events_and_reports(ingest):
    response = ingest(
        {"installId": INSTALL, "app": APP, "events": [event(level="hometown")], "reports": [report()]}
    )
    assert response.status_code == 200
    assert response.json["stored"] == {"events": 1, "reports": 1, "duplicates": 0}
    stored = db.session.scalars(select(GameEvent)).one()
    assert stored.data == {"level": "hometown"}
    assert stored.app_version == "0.1.0 (402)"
    error = db.session.scalars(select(ErrorReport)).one()
    assert error.commit == "abc123"
    assert error.device_model == "Xiaomi Redmi 9"


def test_the_install_id_is_never_stored(ingest):
    ingest({"installId": INSTALL, "app": APP, "events": [event()]})
    player = db.session.scalars(select(Player)).one()
    assert player.player_hash == player_hash(INSTALL, "test-pepper")
    assert INSTALL not in player.player_hash


def test_a_batch_sent_twice_is_stored_once(ingest):
    body = {"installId": INSTALL, "events": [event(), event()], "reports": [report()]}
    assert ingest(body).json["stored"]["duplicates"] == 0
    again = ingest(body)
    assert again.status_code == 200
    assert again.json["stored"] == {"events": 0, "reports": 0, "duplicates": 3}
    assert db.session.scalar(select(func.count()).select_from(GameEvent)) == 2
    assert db.session.scalar(select(func.count()).select_from(Player)) == 1


def test_the_player_keeps_the_newest_details(ingest):
    ingest({"installId": INSTALL, "app": APP, "events": [event()]})
    ingest({"installId": INSTALL, "app": {**APP, "version": "0.2.0 (410)"}, "events": [event()]})
    player = db.session.scalars(select(Player)).one()
    assert player.app_version == "0.2.0 (410)"


def test_a_wrong_clock_dates_the_event_when_it_arrives(ingest):
    far = event()
    far["at"] = "1999-01-01T00:00:00Z"
    ingest({"installId": INSTALL, "events": [far]})
    stored = db.session.scalars(select(GameEvent)).one()
    assert stored.occurred_at > datetime.now(timezone.utc) - timedelta(minutes=1)


def test_an_offline_event_keeps_its_own_date(ingest):
    old = event()
    at = datetime.now(timezone.utc) - timedelta(days=10)
    old["at"] = at.isoformat()
    ingest({"installId": INSTALL, "events": [old]})
    stored = db.session.scalars(select(GameEvent)).one()
    assert abs((stored.occurred_at - at).total_seconds()) < 1


def test_the_key_is_required(ingest):
    assert ingest({"installId": INSTALL}, key="wrong").status_code == 401
    assert ingest({"installId": INSTALL}, key="").status_code == 401


def test_bad_batches_are_refused(ingest):
    assert ingest({"installId": "short"}).status_code == 400
    assert ingest({"installId": INSTALL, "events": [{"id": "x", "type": "ok"}]}).status_code == 400
    assert ingest({"installId": INSTALL, "events": [event("Not Snake")]}).status_code == 400
    assert ingest({"installId": INSTALL, "events": [event() for _ in range(501)]}).status_code == 400
    assert ingest({"installId": INSTALL, "reports": [report(text="x" * 300_000)]}).status_code == 400
    assert ingest({"installId": INSTALL, "events": [event(blob="x" * 5000)]}).status_code == 400
    assert db.session.scalar(select(func.count()).select_from(Player)) == 0


def test_a_body_too_large_is_refused(client):
    response = client.post(
        "/v1/ingest",
        data=b"{" + b" " * (1024 * 1024 + 10) + b"}",
        headers={"X-Stepbound-Key": "test-ingest-key", "Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_the_same_bug_shares_a_fingerprint(ingest):
    ingest(
        {
            "installId": INSTALL,
            "reports": [
                report(),
                report(summary="RangeError (index): Invalid value: Not in inclusive range 0..9: 12"),
                report(summary="Null check operator used on a null value"),
            ],
        }
    )
    prints = db.session.scalars(select(ErrorReport.fingerprint)).all()
    assert len(set(prints)) == 2


def test_forget_removes_the_player_and_their_data(client, ingest):
    ingest({"installId": INSTALL, "events": [event()], "reports": [report()]})
    response = client.post(
        "/v1/forget", json={"installId": INSTALL}, headers={"X-Stepbound-Key": "test-ingest-key"}
    )
    assert response.json == {"forgotten": True}
    for model in (Player, GameEvent, ErrorReport):
        assert db.session.scalar(select(func.count()).select_from(model)) == 0


def test_rate_limit_per_address(app, ingest):
    app.config["INGEST_RATE_LIMIT"] = "2/minute"
    try:
        codes = [
            ingest({"installId": f"{n:032x}"}).status_code for n in range(1, 4)
        ]
    finally:
        app.config["INGEST_RATE_LIMIT"] = "1000/minute"
    assert codes == [200, 200, 429]


def test_rate_limit_per_phone_leaves_the_others_alone(app, ingest):
    app.config["PLAYER_RATE_LIMIT"] = "2/minute"
    try:
        codes = [ingest({"installId": INSTALL}).status_code for _ in range(3)]
        other = ingest({"installId": "f" * 32}).status_code
    finally:
        app.config["PLAYER_RATE_LIMIT"] = "1000/minute"
    assert codes == [200, 200, 429]
    assert other == 200


def test_healthz(client):
    assert client.get("/healthz").json == {"status": "ok"}
