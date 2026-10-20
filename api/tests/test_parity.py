from __future__ import annotations

import json
from pathlib import Path

from app.services.condition import matches
from app.services.project import apply_events

ROOT = Path(__file__).resolve().parents[2]


def test_condition_fixtures():
    rows = json.loads((ROOT / "fixtures" / "conditions" / "shadow.json").read_text(encoding="utf-8"))
    for row in rows:
        assert matches(row["node"], row["facts"]) is row["expected"], row["name"]


def test_shadow_event_fixture_and_server():
    fixture = json.loads((ROOT / "fixtures" / "events" / "shadow.json").read_text(encoding="utf-8"))
    events = []
    for item in fixture["events"]:
        events.append(
            {
                "id": f"00000000-0000-4000-8000-{item['seq']:012d}",
                "seq": item["seq"],
                "device_id": "parity",
                "type": item["type"],
                "payload": item["payload"],
                "created_at": item["created_at"],
            }
        )
    state = apply_events(events)
    for warning in fixture["expect"]["warnings_contains"]:
        assert warning in state["warnings"]
    assert len(state["shadow"]) == fixture["expect"]["shadow_count"]
    last = state["shadow"][-1]
    assert last["nml_in_shadow"] is fixture["expect"]["last_nml"]
    assert last["opp_dz_in_shadow"] is fixture["expect"]["last_opp"]


def test_shadow_phased_projection():
    events = [
        {
            "id": "00000000-0000-4000-8000-000000000001",
            "seq": 1,
            "device_id": "a",
            "type": "game_started",
            "payload": {"first_player": "me", "units": [{"list_unit_id": 1, "name": "X"}]},
            "created_at": "2026-10-15T12:00:00Z",
        },
        {
            "id": "00000000-0000-4000-8000-000000000002",
            "seq": 2,
            "device_id": "a",
            "type": "phase_advanced",
            "payload": {},
            "created_at": "2026-10-15T12:00:01Z",
        },
        {
            "id": "00000000-0000-4000-8000-000000000003",
            "seq": 3,
            "device_id": "a",
            "type": "shadow_set",
            "payload": {"nml_controlled": 2, "nml_total": 4, "opp_dz_controlled": 0, "opp_dz_total": 1},
            "created_at": "2026-10-15T12:00:02Z",
        },
    ]
    state = apply_events(events)
    assert state["shadow"][0]["nml_in_shadow"] is True
    assert state["shadow"][0]["opp_dz_in_shadow"] is False
