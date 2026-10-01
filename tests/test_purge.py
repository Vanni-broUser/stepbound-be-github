from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from stepbound_be.cli import purge
from stepbound_be.extensions import db
from stepbound_be.models import ErrorReport, GameEvent, Player
from tests.test_ingest import event, report


def test_purge_removes_what_is_past_retention(app, ingest):
    ingest({"installId": "0" * 32, "events": [event(), event()], "reports": [report()]})
    ingest({"installId": "1" * 32, "events": [event()]})
    long_ago = datetime.now(timezone.utc) - timedelta(days=400)
    first = db.session.scalar(select(Player.id).order_by(Player.id))
    db.session.execute(update(GameEvent).where(GameEvent.player_id == first).values(occurred_at=long_ago))
    db.session.execute(update(ErrorReport).values(occurred_at=long_ago))
    db.session.execute(update(Player).where(Player.id == first).values(last_seen=long_ago))
    db.session.commit()

    assert purge() == {"events": 2, "reports": 1, "players": 1}
    assert db.session.scalar(select(func.count()).select_from(GameEvent)) == 1
    assert db.session.scalar(select(func.count()).select_from(Player)) == 1


def test_the_cli_command(app):
    result = app.test_cli_runner().invoke(args=["purge"])
    assert "removed 0 events" in result.output
