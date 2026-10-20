from __future__ import annotations

import uuid

from app.services.project import apply_events


def ev(seq: int, kind: str, payload: dict, at: str = "2026-10-15T12:00:00Z") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "game_id": str(uuid.uuid4()),
        "seq": seq,
        "device_id": "device-a",
        "type": kind,
        "payload": payload,
        "undoes_event_id": payload.get("undoes_event_id"),
        "created_at": at,
    }


def started() -> dict:
    return ev(
        1,
        "game_started",
        {
            "list_version_id": 1,
            "bundle_etag": "abc",
            "first_player": "me",
            "cp_me": 0,
            "units": [
                {"list_unit_id": 1, "name": "Daemonettes"},
                {"list_unit_id": 2, "name": "Unidade Assault Fixture"},
            ],
            "attachments": [{"leader_list_unit_id": 4, "bodyguard_list_unit_id": 3}],
        },
        "2026-10-15T12:00:00Z",
    )


def test_advance_shooting_and_cp():
    start = started()
    events = [
        start,
        ev(2, "cp_changed", {"delta": 1, "reason": "command_phase", "player": "me"}, "2026-10-15T12:00:01Z"),
        ev(3, "phase_advanced", {}, "2026-10-15T12:00:02Z"),
        ev(4, "phase_advanced", {}, "2026-10-15T12:00:03Z"),
        ev(
            5,
            "unit_state_set",
            {"list_unit_id": 1, "patch": {"moved": "advanced"}},
            "2026-10-15T12:00:04Z",
        ),
        ev(6, "phase_advanced", {}, "2026-10-15T12:00:05Z"),
        ev(7, "phase_advanced", {}, "2026-10-15T12:00:06Z"),
    ]
    state = apply_events(events)
    assert state["phase"] == "shooting"
    assert state["cp"]["me"] == 1
    assert state["live"][1]["moved"] == "advanced"
    assert state["attachments"][0]["leader_list_unit_id"] == 4


def test_undo_restores_movement():
    start = started()
    move = ev(
        2,
        "unit_state_set",
        {"list_unit_id": 1, "patch": {"moved": "advanced"}},
        "2026-10-15T12:00:01Z",
    )
    undo = ev(
        3,
        "undo",
        {"undoes_event_id": move["id"]},
        "2026-10-15T12:00:02Z",
    )
    state = apply_events([start, move, undo])
    assert state["live"][1]["moved"] == "none"


def test_cp_does_not_go_negative_without_override():
    start = started()
    state = apply_events(
        [
            start,
            ev(2, "cp_changed", {"delta": -1, "reason": "manual", "player": "me"}, "2026-10-15T12:00:01Z"),
        ]
    )
    assert state["cp"]["me"] == 0
    assert "cp_blocked" in state["warnings"]


def test_stratagem_limit_and_override():
    start = started()
    gain = ev(2, "cp_changed", {"delta": 2, "reason": "command_phase", "player": "me"}, "2026-10-15T12:00:01Z")
    first = ev(
        3,
        "stratagem_used",
        {"stratagem_name": "Exemplo", "cp_spent": 1, "use_limit": "per_phase", "player": "me"},
        "2026-10-15T12:00:02Z",
    )
    second = ev(
        4,
        "stratagem_used",
        {"stratagem_name": "Exemplo", "cp_spent": 1, "use_limit": "per_phase", "player": "me"},
        "2026-10-15T12:00:03Z",
    )
    state = apply_events([start, gain, first, second])
    assert state["cp"]["me"] == 1
    assert len(state["stratagem_uses"]) == 1
    assert "stratagem_limit" in state["warnings"]
    third = ev(
        5,
        "stratagem_used",
        {
            "stratagem_name": "Exemplo",
            "cp_spent": 1,
            "use_limit": "per_phase",
            "player": "me",
            "limit_overridden": True,
        },
        "2026-10-15T12:00:04Z",
    )
    state = apply_events([start, gain, first, second, third])
    assert any(item["limit_overridden"] for item in state["stratagem_uses"])
    assert state["cp"]["me"] == 0


def test_battle_shock_persists_until_passed():
    start = started()
    events = [
        start,
        ev(2, "phase_advanced", {}, "2026-10-15T12:00:01Z"),
        ev(3, "battleshock_result", {"list_unit_id": 1, "passed": False}, "2026-10-15T12:00:02Z"),
    ]
    state = apply_events(events)
    assert state["live"][1]["battle_shocked"] is True
    seq = 4
    for _ in range(24):
        events.append(ev(seq, "phase_advanced", {}, f"2026-10-15T12:01:{seq:02d}Z"))
        seq += 1
        state = apply_events(events)
        if state["round"] == 2 and state["phase"] == "command" and state["player"] == "me":
            break
    assert state["player"] == "me"
    assert state["phase"] == "command"
    assert state["round"] == 2
    assert state["live"][1]["battle_shocked"] is True
    events.append(ev(seq, "phase_advanced", {}, f"2026-10-15T12:02:00Z"))
    seq += 1
    events.append(
        ev(seq, "battleshock_result", {"list_unit_id": 1, "passed": True}, f"2026-10-15T12:02:01Z")
    )
    state = apply_events(events)
    assert state["live"][1]["battle_shocked"] is False
    pass_id = events[-1]["id"]
    events.append(ev(seq + 1, "undo", {"undoes_event_id": pass_id}, "2026-10-15T12:02:02Z"))
    state = apply_events(events)
    assert state["live"][1]["battle_shocked"] is True


def test_engaged_at_fight_start_on_entering_fight():
    events = [
        started(),
        ev(2, "unit_state_set", {"list_unit_id": 1, "patch": {"engaged": True}}, "2026-10-15T12:00:01Z"),
    ]
    seq = 3
    state = apply_events(events)
    while state["phase"] != "fight" and seq < 20:
        events.append(ev(seq, "phase_advanced", {}, f"2026-10-15T12:00:{seq:02d}Z"))
        seq += 1
        state = apply_events(events)
    assert state["phase"] == "fight"
    assert state["live"][1]["engaged_at_fight_start"] is True
    events.append(
        ev(seq, "unit_state_set", {"list_unit_id": 1, "patch": {"engaged": False}}, "2026-10-15T12:01:00Z")
    )
    state = apply_events(events)
    assert state["live"][1]["engaged"] is False
    assert state["live"][1]["engaged_at_fight_start"] is True


def test_lane_survives_new_turn():
    events = [
        started(),
        ev(2, "unit_state_set", {"list_unit_id": 1, "patch": {"lane": "left"}}, "2026-10-15T12:00:01Z"),
        ev(3, "unit_state_set", {"list_unit_id": 2, "patch": {"lane": "middle"}}, "2026-10-15T12:00:02Z"),
        ev(4, "unit_state_set", {"list_unit_id": 2, "patch": {"lane": "home"}}, "2026-10-15T12:00:03Z"),
    ]
    seq = 5
    state = apply_events(events)
    for _ in range(24):
        events.append(ev(seq, "phase_advanced", {}, f"2026-10-15T12:01:{seq:02d}Z"))
        seq += 1
        state = apply_events(events)
        if state["round"] == 2:
            break
    assert state["round"] == 2
    assert state["live"][1]["lane"] == "left"
    assert state["live"][2]["lane"] == "home"
    assert "bad_lane" in state["warnings"]


def test_effect_choice_replaces_within_turn():
    events = [
        started(),
        ev(2, "effect_chosen", {"effect_id": 7, "list_unit_id": 1, "options": ["A", "B"], "count": 2}, "2026-10-15T12:00:01Z"),
        ev(3, "effect_chosen", {"effect_id": 7, "list_unit_id": 1, "options": ["B", "C"], "count": 2}, "2026-10-15T12:00:02Z"),
        ev(4, "effect_chosen", {"effect_id": 8, "options": ["Vow"], "scope": "battle"}, "2026-10-15T12:00:03Z"),
    ]
    state = apply_events(events)
    assert [item["options"] for item in state["choices"]] == [["B", "C"], ["Vow"]]
    assert state["choices"][1]["scope"] == "battle"


def test_replay_is_deterministic():
    start = started()
    events = [start, ev(2, "phase_advanced", {}, "2026-10-15T12:00:01Z")]
    assert apply_events(events)["phase"] == apply_events(list(reversed(events)))["phase"]
