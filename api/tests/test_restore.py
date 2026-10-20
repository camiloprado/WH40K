from tests.test_api import TEXT, _client


def test_restore_then_create_list():
    client = _client()
    parsed = client.post("/api/v1/imports/parse", json={"raw_text": TEXT}).json()
    created = client.post(
        "/api/v1/imports",
        json={
            "raw_text": TEXT,
            "parse_hash": parsed["parse_hash"],
            "target": {"new_list_name": "Antes do restore"},
            "resolutions": {},
        },
    )
    assert created.status_code == 200, created.text
    backup = client.get("/api/v1/backup")
    assert backup.status_code == 200
    assert "sessions" not in backup.json()["tables"]
    restored = client.post("/api/v1/restore", json={"confirm": "RESTAURAR", "data": backup.json()})
    assert restored.status_code == 200, restored.text
    again = client.post(
        "/api/v1/imports",
        json={
            "raw_text": TEXT,
            "parse_hash": parsed["parse_hash"],
            "target": {"new_list_name": "Depois do restore"},
            "resolutions": {},
        },
    )
    assert again.status_code == 200, again.text
    names = [item["name"] for item in client.get("/api/v1/lists").json()]
    assert "Antes do restore" in names
    assert "Depois do restore" in names
