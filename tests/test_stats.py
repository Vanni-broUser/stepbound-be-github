import uuid
from datetime import datetime, timedelta, timezone

from tests.test_ingest import event, report

PLAYERS = [f"{n:032x}" for n in range(1, 4)]


def seed(ingest):
    for index, install in enumerate(PLAYERS):
        events = [
            event("app_opened"),
            event("session_ended", seconds=600),
            event("level_started", level="hometown"),
            event("place_entered", level="hometown", place="Porto"),
            event("zombie_killed", level="hometown", place="Porto", kind="wanderer"),
        ]
        if index < 2:
            events.append(
                event(
                    "level_completed",
                    level="hometown",
                    zombiesKilled=10 + index * 2,
                    zombiesTotal=20,
                    steps=1000,
                    playSeconds=1800,
                )
            )
        else:
            events.append(event("player_died", level="hometown", place="Porto", killer="brute"))
        ingest({"installId": install, "app": {"platform": "android", "version": "0.1.0"}, "events": events})


def test_stats_need_the_admin_token(client):
    assert client.get("/v1/stats/overview").status_code == 401
    assert (
        client.get("/v1/stats/overview", headers={"Authorization": "Bearer nope"}).status_code
        == 401
    )


def test_overview(ingest, admin):
    seed(ingest)
    body = admin("/v1/stats/overview").json
    assert body["players_total"] == 3
    assert body["players_active"] == 3
    assert body["sessions"] == 3
    assert body["avg_session_seconds"] == 600
    assert body["total_play_hours"] == 0.5
    assert body["daily_active"][-1]["players"] == 3
    assert body["platforms"] == [{"platform": "android", "players": 3}]


def test_levels(ingest, admin):
    seed(ingest)
    (level,) = admin("/v1/stats/levels").json["levels"]
    assert level["level"] == "hometown"
    assert level["players_started"] == 3
    assert level["players_completed"] == 2
    assert level["completion_rate"] == 0.667
    assert level["players_died"] == 1
    assert level["avg_zombies_killed"] == 11
    assert level["avg_play_minutes"] == 30


def test_zombies_and_places(ingest, admin):
    seed(ingest)
    zombies = admin("/v1/stats/zombies").json
    assert zombies["killed"] == [{"kind": "wanderer", "kills": 3, "players": 3}]
    assert zombies["killed_player"] == [{"killer": "brute", "deaths": 1}]
    places = admin("/v1/stats/places").json
    assert places["reached"] == [{"level": "hometown", "place": "Porto", "players": 3}]
    assert places["deaths"] == [{"level": "hometown", "place": "Porto", "deaths": 1}]


def test_old_events_are_left_out(ingest, admin):
    old = event("level_started", level="rome")
    old["at"] = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    ingest({"installId": PLAYERS[0], "events": [old]})
    assert admin("/v1/stats/levels?days=30").json["levels"] == []
    assert admin("/v1/stats/levels?days=60").json["levels"][0]["level"] == "rome"


def test_errors_grouped(ingest, admin):
    ingest({"installId": PLAYERS[0], "reports": [report(), report()]})
    ingest({"installId": PLAYERS[1], "reports": [report(), report(summary="Bad state: no element")]})
    groups = admin("/v1/errors").json["errors"]
    assert [(g["reports"], g["players"]) for g in groups] == [(3, 2), (1, 1)]
    detail = admin(f"/v1/errors/{groups[0]['latest_id']}")
    assert detail.json["body"].startswith("RAPPORTO DI ERRORE")
    text = admin(f"/v1/errors/{groups[0]['latest_id']}?format=text")
    assert text.content_type.startswith("text/plain")
    assert admin(f"/v1/errors/{uuid.uuid4()}").status_code == 404
    assert admin("/v1/errors/not-a-uuid").status_code == 404
