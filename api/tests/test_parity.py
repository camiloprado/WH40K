from __future__ import annotations

import json
from pathlib import Path

from app.services.condition import matches
from app.services.project import apply_events

ROOT = Path(__file__).resolve().parents[2]


def test_condition_fixtures():
    rows = json.loads((ROOT / "fixtures" / "conditions" / "shadow.json").read_text(encoding="utf-8-sig"))
    for row in rows:
        assert matches(row["node"], row["facts"]) is row["expected"], row["name"]


def test_shadow_event_fixture_and_server():
    fixture = json.loads((ROOT / "fixtures" / "events" / "shadow.json").read_text(encoding="utf-8-sig"))
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


def _load_events(name: str) -> tuple[list[dict], dict]:
    fixture = json.loads((ROOT / "fixtures" / "events" / name).read_text(encoding="utf-8-sig"))
    events = [
        {
            "id": f"00000000-0000-4000-8000-{item['seq']:012d}",
            "seq": item["seq"],
            "device_id": "parity",
            "type": item["type"],
            "payload": item["payload"],
            "undoes_event_id": item.get("undoes_event_id"),
            "created_at": item["created_at"],
        }
        for item in fixture["events"]
    ]
    return events, fixture["expect"]


def test_c10_event_fixture():
    events, expect = _load_events("c10_blank_turn.json")
    state = apply_events(events)
    assert state["player"] == expect["player"]
    assert state["phase"] == expect["phase"]
    assert state["live"][1]["fought"] is expect["fought"]
    assert state["live"][1]["engaged"] is expect["engaged"]


def test_c12_event_fixture():
    events, expect = _load_events("c12_per_turn.json")
    state = apply_events(events)
    assert len(state["stratagem_uses"]) == expect["uses"]
    assert state["cp"]["me"] == expect["cp_me"]
    assert expect["no_warning"] not in state["warnings"]


def test_c17_event_fixture():
    events, expect = _load_events("c17_phases_v2.json")
    state = apply_events(events)
    assert state["phase"] == expect["phase"]
    assert state["round"] == expect["round"]
    assert state["player"] == expect["player"]


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
