import uuid

from tests.test_api import TEXT, _client


def _version(client) -> int:
    parsed = client.post("/api/v1/imports/parse", json={"raw_text": TEXT}).json()
    created = client.post(
        "/api/v1/imports",
        json={"raw_text": TEXT, "parse_hash": parsed["parse_hash"], "target": {"new_list_name": "Efeitos"}, "resolutions": {}},
    )
    assert created.status_code == 200, created.text
    return created.json()["version_id"]


def test_character_choice_effect_reaches_bundle_with_units():
    client = _client()
    version_id = _version(client)
    units = client.get(f"/api/v1/versions/{version_id}").json()["units"]
    hero = next(unit for unit in units if unit["datasheet_name"] == "Poxbringer")
    ability = client.post(
        "/api/v1/abilities",
        json={"kind": "unit", "datasheet_id": hero["datasheet_id"], "name": "Escolha do herói", "is_hypothesis": True},
    )
    assert ability.status_code == 200, ability.text
    bad = client.post(
        f"/api/v1/abilities/{ability.json()['id']}/effects",
        json={"phase": "command", "owner_label": "Herói", "effect_text": "x", "choice_options": ["A"], "choice_count": 2},
    )
    assert bad.status_code == 422
    effect = client.post(
        f"/api/v1/abilities/{ability.json()['id']}/effects",
        json={
            "phase": "command",
            "timing": "start",
            "effect_kind": "prompt",
            "owner_label": "Herói",
            "effect_text": "Escolha dois",
            "choice_options": ["A", "B", "C"],
            "choice_count": 2,
            "choice_scope": "turn",
        },
    )
    assert effect.status_code == 200, effect.text
    bundle = client.get(f"/api/v1/versions/{version_id}/bundle").json()
    row = next(item for item in bundle["rule_effects"] if item["id"] == effect.json()["id"])
    assert row["unit_ids"] == [hero["id"]]
    assert row["choice_options"] == ["A", "B", "C"]
    assert row["choice_count"] == 2
    listed = client.get("/api/v1/effects").json()
    assert any(item["id"] == row["id"] for item in listed)
    assert client.request("DELETE", f"/api/v1/effects/{row['id']}", json={}).status_code == 200


def test_effect_chosen_event_is_accepted_by_sync():
    client = _client()
    version_id = _version(client)
    tag = client.get(f"/api/v1/versions/{version_id}/bundle").headers["etag"]
    game_id = str(uuid.uuid4())
    game = client.post("/api/v1/games", json={"id": game_id, "list_version_id": version_id, "bundle_etag": tag, "first_player": "me"})
    assert game.status_code == 200, game.text
    events = [
        {
            "id": "11111111-1111-4111-8111-000000000001",
            "seq": 1,
            "device_id": "d",
            "type": "game_started",
            "payload": {"first_player": "me", "units": []},
            "created_at": "2026-10-15T12:00:00Z",
        },
        {
            "id": "11111111-1111-4111-8111-000000000002",
            "seq": 2,
            "device_id": "d",
            "type": "effect_chosen",
            "payload": {"effect_id": 1, "options": ["Vow"], "scope": "battle"},
            "created_at": "2026-10-15T12:00:01Z",
        },
    ]
    synced = client.post("/api/v1/games/sync", json={"game_id": game_id, "events": events})
    assert synced.status_code == 200, synced.text
    assert len(synced.json()["accepted"]) == 2
