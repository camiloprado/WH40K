import hashlib
import os
import uuid
from pathlib import Path

os.environ["TOKEN_HASH_FILE"] = "data/missing-token-hash"
TOKEN = "test-token-value"
os.environ["APP_TOKEN_HASH"] = hashlib.sha256(TOKEN.encode()).hexdigest()

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "fixtures" / "text" / "daemons_1975.txt").read_text(encoding="utf-8")


def _client() -> TestClient:
    get_settings.cache_clear()
    import app.db as database

    database._engine = None
    database._factory = None
    client = TestClient(create_app())
    response = client.post("/api/v1/session", json={"token": TOKEN}, headers={"X-App": "wh40k"})
    assert response.status_code == 200, response.text
    raw = response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
    client.headers.update({"X-App": "wh40k", "Cookie": f"__Host-session={raw}"})
    return client


def test_import_1975_leaders_and_immutable_snapshot():
    client = _client()
    parsed = client.post("/api/v1/imports/parse", json={"raw_text": TEXT, "format_hint": "nr_text_simple"})
    assert parsed.status_code == 200, parsed.text
    body = parsed.json()
    assert body["header"]["points_sum"] == 1975
    names = {(pair["leader_name"], pair["bodyguard_name"]) for pair in body["leader_pairs"]}
    assert ("Poxbringer", "Plaguebearers") in names
    created = client.post(
        "/api/v1/imports",
        json={
            "raw_text": TEXT,
            "parse_hash": body["parse_hash"],
            "target": {"new_list_name": "Daemons"},
            "resolutions": {},
        },
    )
    assert created.status_code == 200, created.text
    version_id = created.json()["version_id"]
    view = client.get(f"/api/v1/versions/{version_id}")
    assert view.status_code == 200
    payload = view.json()
    assert payload["points_sum"] == 1975
    assert payload["points_state"] == "exact"
    by_id = {unit["id"]: unit["datasheet_name"] for unit in payload["units"]}
    pairs = {
        (by_id[item["leader_list_unit_id"]], by_id[item["bodyguard_list_unit_id"]])
        for item in payload["attachments"]
    }
    assert ("Poxbringer", "Plaguebearers") in pairs
    frozen = client.patch(f"/api/v1/versions/{version_id}", json={"points": 1})
    assert frozen.status_code == 409
    assert frozen.json()["code"] == "version_immutable"
    changed = client.post(
        "/api/v1/imports",
        json={"raw_text": TEXT + "\n", "parse_hash": body["parse_hash"], "target": {"list_id": created.json()["list_id"]}, "resolutions": {}},
    )
    assert changed.status_code == 409
    assert changed.json()["code"] == "parse_changed"
    leader = next(unit["id"] for unit in payload["units"] if unit["datasheet_name"] == "Poxbringer")
    again = client.put(
        f"/api/v1/versions/{version_id}/attachments",
        json={"pairs": [{"leader_list_unit_id": leader, "bodyguard_list_unit_id": leader}]},
    )
    assert again.status_code == 409
    bundle = client.get(f"/api/v1/versions/{version_id}/bundle")
    assert bundle.status_code == 200
    tag = bundle.headers["etag"]
    assert client.get(f"/api/v1/versions/{version_id}/bundle", headers={"If-None-Match": tag}).status_code == 304
    game_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    opened = client.post(
        "/api/v1/games",
        json={"id": game_id, "list_version_id": version_id, "bundle_etag": tag, "first_player": "me"},
    )
    assert opened.status_code == 200, opened.text
    event = {
        "id": event_id,
        "seq": 1,
        "device_id": "device-a",
        "type": "game_started",
        "created_at": "2026-10-15T12:00:00+00:00",
        "payload": {"first_player": "me", "cp_me": 0, "units": []},
    }
    first = client.post("/api/v1/games/sync", json={"game_id": game_id, "events": [event]})
    second = client.post("/api/v1/games/sync", json={"game_id": game_id, "events": [event]})
    assert first.status_code == 200, first.text
    assert event_id in first.json()["accepted"]
    assert event_id in second.json()["duplicates"]
    assert second.json()["last_seq"] == 1


def test_finished_game_does_not_block_deleting_the_list():
    client = _client()
    parsed = client.post("/api/v1/imports/parse", json={"raw_text": TEXT}).json()
    created = client.post(
        "/api/v1/imports",
        json={"raw_text": TEXT, "parse_hash": parsed["parse_hash"], "target": {"new_list_name": "Daemons"}, "resolutions": {}},
    )
    assert created.status_code == 200, created.text
    list_id = created.json()["list_id"]
    version_id = created.json()["version_id"]
    units = client.get(f"/api/v1/versions/{version_id}").json()["units"]
    tag = client.get(f"/api/v1/versions/{version_id}/bundle").headers["etag"]
    game_id = str(uuid.uuid4())
    opened = client.post(
        "/api/v1/games",
        json={"id": game_id, "list_version_id": version_id, "bundle_etag": tag, "first_player": "me"},
    )
    assert opened.status_code == 200, opened.text
    synced = client.post(
        "/api/v1/games/sync",
        json={
            "game_id": game_id,
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "seq": 1,
                    "device_id": "device-a",
                    "type": "game_started",
                    "created_at": "2026-10-15T12:00:00+00:00",
                    "payload": {
                        "first_player": "me",
                        "units": [{"list_unit_id": units[0]["id"], "name": units[0]["datasheet_name"]}],
                    },
                }
            ],
        },
    )
    assert synced.status_code == 200, synced.text
    blocked = client.request("DELETE", f"/api/v1/lists/{list_id}", json={"confirm": "EXCLUIR"})
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "list_in_use"
    finished = client.patch(f"/api/v1/games/{game_id}", json={"status": "finished", "result": "draw"})
    assert finished.status_code == 200, finished.text
    removed = client.request("DELETE", f"/api/v1/lists/{list_id}", json={"confirm": "EXCLUIR"})
    assert removed.status_code == 200, removed.text
    kept = client.get(f"/api/v1/games/{game_id}")
    assert kept.status_code == 200, kept.text
    body = kept.json()
    assert body["status"] == "finished"
    assert body["result"] == "draw"
    assert body["list_label"] == "Daemons"
    assert body["list_version_id"] is None
