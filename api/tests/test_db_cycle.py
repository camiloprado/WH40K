"""DB1 / DB3 — ciclo 0013 e eventos rejeitados."""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import get_settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
TEXT = (REPO / "fixtures" / "text" / "daemons_1975.txt").read_text(encoding="utf-8")
TOKEN = "test-token-value"


def _alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return config


def _client() -> TestClient:
    os.environ["APP_TOKEN_HASH"] = hashlib.sha256(TOKEN.encode()).hexdigest()
    os.environ["TOKEN_HASH_FILE"] = "data/missing-token-hash"
    get_settings.cache_clear()
    import app.db as database

    database._engine = None
    database._factory = None
    client = TestClient(create_app())
    response = client.post("/api/v1/session", json={"token": TOKEN}, headers={"X-App": "wh40k"})
    assert response.status_code == 200, response.text
    raw = response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
    client.headers.update({"X-App": "wh40k", "Cookie": f"session={raw}"})
    return client


def _open_game(client: TestClient) -> str:
    parsed = client.post("/api/v1/imports/parse", json={"raw_text": TEXT}).json()
    created = client.post(
        "/api/v1/imports",
        json={
            "raw_text": TEXT,
            "parse_hash": parsed["parse_hash"],
            "target": {"new_list_name": f"DB-{uuid.uuid4().hex[:8]}"},
            "resolutions": {},
        },
    )
    assert created.status_code == 200, created.text
    version_id = created.json()["version_id"]
    tag = client.get(f"/api/v1/versions/{version_id}/bundle").headers["etag"]
    game_id = str(uuid.uuid4())
    opened = client.post(
        "/api/v1/games",
        json={"id": game_id, "list_version_id": version_id, "bundle_etag": tag, "first_player": "me"},
    )
    assert opened.status_code == 200, opened.text
    started = {
        "id": str(uuid.uuid4()),
        "seq": 1,
        "device_id": "device-a",
        "type": "game_started",
        "created_at": "2026-10-15T12:00:00+00:00",
        "payload": {"first_player": "me", "cp_me": 0, "units": []},
    }
    synced = client.post("/api/v1/games/sync", json={"game_id": game_id, "events": [started]})
    assert synced.status_code == 200, synced.text
    return game_id


def test_db3_rejected_unknown_type():
    client = _client()
    game_id = _open_game(client)
    bad = {
        "id": str(uuid.uuid4()),
        "seq": 99,
        "device_id": "device-a",
        "type": "xyz_unknown",
        "created_at": "2026-10-15T12:00:00+00:00",
        "payload": {},
    }
    res = client.post("/api/v1/games/sync", json={"game_id": game_id, "events": [bad]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert bad["id"] not in body.get("accepted", [])
    assert bad["id"] not in body.get("duplicates", [])
    rejected = body.get("rejected") or []
    assert any(item["id"] == bad["id"] for item in rejected)


def test_db1_shadow_reupgrade_allows_two_phases():
    """upgrade → down 0012 → up, depois 2 shadow_set na mesma rodada."""
    config = _alembic_config()
    try:
        command.downgrade(config, "0012_game_result")
        command.upgrade(config, "head")
        client = _client()
        game_id = _open_game(client)
        events = [
            {
                "id": str(uuid.uuid4()),
                "seq": 2,
                "device_id": "device-a",
                "type": "shadow_set",
                "created_at": "2026-10-15T12:00:01+00:00",
                "payload": {
                    "phase": "command",
                    "turn_player": "me",
                    "nml_in_shadow": True,
                    "opp_dz_in_shadow": False,
                },
            },
            {
                "id": str(uuid.uuid4()),
                "seq": 3,
                "device_id": "device-a",
                "type": "phase_advanced",
                "created_at": "2026-10-15T12:00:02+00:00",
                "payload": {},
            },
            {
                "id": str(uuid.uuid4()),
                "seq": 4,
                "device_id": "device-a",
                "type": "shadow_set",
                "created_at": "2026-10-15T12:00:03+00:00",
                "payload": {
                    "phase": "battle_shock",
                    "turn_player": "me",
                    "nml_in_shadow": False,
                    "opp_dz_in_shadow": True,
                },
            },
        ]
        res = client.post("/api/v1/games/sync", json={"game_id": game_id, "events": events})
        assert res.status_code == 200, res.text
        assert not res.json().get("rejected")
        engine = create_engine(os.environ["DATABASE_URL"])
        with engine.connect() as conn:
            count = conn.execute(
                text(
                    "SELECT count(*) FROM faction_round_states "
                    "WHERE game_id = :g AND round = 1 AND state_key = 'shadow_of_chaos'"
                ),
                {"g": game_id},
            ).scalar()
        assert count == 2
    finally:
        command.upgrade(config, "head")
