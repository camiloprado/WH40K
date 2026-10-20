from __future__ import annotations

import copy
import uuid

con_lstPhases = ["round_start", "command", "battle_shock", "movement", "shooting", "charge", "fight", "end_of_turn"]
con_setPatchFields = {
    "moved",
    "shot",
    "charged",
    "fought",
    "engaged",
    "engaged_at_fight_start",
    "on_action",
    "action_name",
    "battle_shocked",
    "below_half",
    "destroyed",
    "in_reserves",
    "lane",
}
con_setLanes = {"left", "center", "right", "home"}
con_setChoiceScopes = {"turn", "round", "battle"}

PHASES = con_lstPhases
PATCH_FIELDS = con_setPatchFields
LANES = con_setLanes
CHOICE_SCOPES = con_setChoiceScopes


def apply_events(events: list[dict]) -> dict:
    var_lstOrdered = sorted(events, key=lambda item: (item["created_at"], item["device_id"], item["seq"]))
    var_setInactive = _inactive(var_lstOrdered)
    var_dctState = _empty()
    var_dctSeen: dict[int, str] = {}
    for var_dctEvent in var_lstOrdered:
        var_strOther = var_dctSeen.get(var_dctEvent["seq"])
        if var_strOther and var_strOther != var_dctEvent["device_id"]:
            var_dctState["warnings"].append("seq_collision")
        var_dctSeen.setdefault(var_dctEvent["seq"], var_dctEvent["device_id"])
        if var_dctEvent["id"] in var_setInactive or var_dctEvent["type"] == "undo":
            continue
        _apply(var_dctState, var_dctEvent)
        _snapshot(var_dctState)
    return var_dctState


def _inactive(events: list[dict]) -> set[str]:
    inactive: set[str] = set()
    while True:
        found: set[str] = set()
        for event in events:
            if event["type"] == "undo" and event["id"] not in inactive:
                target = event.get("undoes_event_id") or event["payload"].get("undoes_event_id")
                if target:
                    found.add(target)
        if found == inactive:
            return inactive
        inactive = found


def _empty() -> dict:
    return {
        "status": "active",
        "result": None,
        "list_label": None,
        "round": 1,
        "player": "me",
        "phase": "command",
        "first_player": "me",
        "list_version_id": None,
        "bundle_etag": None,
        "opponent_name": None,
        "opponent_faction": None,
        "mission_name": None,
        "cp": {"me": 0, "opponent": 0},
        "vp": {"me": 0, "opponent": 0},
        "attachments": [],
        "live": {},
        "unit_states": [],
        "turns": [],
        "stratagem_uses": [],
        "ledger": [],
        "objectives": [],
        "scores": [],
        "shadow": [],
        "battle_shock": [],
        "choices": [],
        "warnings": [],
        "started": False,
    }


def _blank(unit_id: int, name: str, round_no: int, previous: dict | None) -> dict:
    return {
        "list_unit_id": int(unit_id),
        "name": name,
        "round": round_no,
        "player": "me",
        "moved": "none",
        "shot": False,
        "charged": False,
        "fought": False,
        "engaged": bool(previous and previous["engaged"]),
        "engaged_at_fight_start": False,
        "on_action": False,
        "action_name": None,
        "battle_shocked": bool(previous and previous["battle_shocked"]),
        "below_half": bool(previous and previous["below_half"]),
        "destroyed": bool(previous and previous["destroyed"]),
        "in_reserves": bool(previous and previous["in_reserves"]),
        "lane": previous["lane"] if previous else "center",
        "overrides": [],
    }


def _snapshot(state: dict) -> None:
    fresh = []
    current = {(row["list_unit_id"], row["round"], row["player"]) for row in state["live"].values()}
    for row in state["unit_states"]:
        key = (row["list_unit_id"], row["round"], row["player"])
        if key not in current:
            fresh.append(row)
    fresh.extend(copy.deepcopy(row) for row in state["live"].values())
    state["unit_states"] = fresh


def _open_turn(state: dict, event: dict) -> None:
    for turn in state["turns"]:
        if turn["ended_at"] is None:
            turn["ended_at"] = event["created_at"]
    state["turns"].append(
        {
            "round": state["round"],
            "player": state["player"],
            "phase": state["phase"],
            "started_at": event["created_at"],
            "ended_at": None,
        }
    )


def _roll(state: dict) -> None:
    for unit_id, prev in list(state["live"].items()):
        state["live"][unit_id] = _blank(unit_id, prev["name"], state["round"], prev)


def _apply(state: dict, event: dict) -> None:
    kind = event["type"]
    payload = event["payload"]
    if kind == "game_started":
        state["started"] = True
        state["list_version_id"] = payload.get("list_version_id")
        state["bundle_etag"] = payload.get("bundle_etag")
        state["first_player"] = payload.get("first_player") or "me"
        state["player"] = state["first_player"]
        state["phase"] = "round_start"
        state["round"] = 1
        state["opponent_name"] = payload.get("opponent_name")
        state["opponent_faction"] = payload.get("opponent_faction")
        state["mission_name"] = payload.get("mission_name")
        state["cp"]["me"] = int(payload.get("cp_me") or 0)
        state["cp"]["opponent"] = int(payload.get("cp_opponent") or 0)
        state["attachments"] = payload.get("attachments") or []
        for unit in payload.get("units") or []:
            state["live"][int(unit["list_unit_id"])] = _blank(
                unit["list_unit_id"], unit.get("name") or "", 1, None
            )
        _open_turn(state, event)
        return
    if not state["started"]:
        state["warnings"].append("missing_game_started")
        return
    if kind == "phase_advanced":
        index = PHASES.index(state["phase"])
        entered_my_command = False
        if index < len(PHASES) - 1:
            state["phase"] = PHASES[index + 1]
        else:
            other = "opponent" if state["player"] == "me" else "me"
            if state["player"] != state["first_player"]:
                state["round"] = min(10, state["round"] + 1)
                state["player"] = state["first_player"]
            else:
                state["player"] = other
            state["phase"] = "round_start"
            entered_my_command = state["player"] == "me"
        if entered_my_command:
            _roll(state)
        if state["phase"] == "fight":
            for unit in state["live"].values():
                unit["engaged_at_fight_start"] = bool(unit["engaged"])
        _open_turn(state, event)
        return
    if kind == "unit_state_set":
        unit = state["live"].get(int(payload["list_unit_id"]))
        if unit is None:
            state["warnings"].append("unknown_unit")
            return
        for key, value in (payload.get("patch") or {}).items():
            if key == "lane" and value not in LANES:
                state["warnings"].append("bad_lane")
                continue
            if key in PATCH_FIELDS:
                unit[key] = value
        if payload.get("overrides"):
            unit["overrides"].extend(payload["overrides"])
        return
    if kind == "cp_changed":
        var_strPlayer = payload.get("player") or state["player"]
        var_intDelta = int(payload.get("delta") or 0)
        var_strReason = payload.get("reason") or "manual"
        if var_strReason == "command_phase":
            var_strReason = "core_cp"
        if var_strReason == "core_cp" and state["phase"] == "command":
            var_boolTwice = any(
                item["round"] == state["round"]
                and item["phase"] == "command"
                and item["player"] == var_strPlayer
                and item["reason"] == "core_cp"
                for item in state["ledger"]
            )
            if var_boolTwice:
                state["warnings"].append("core_cp_twice")
        if var_intDelta > 0 and var_strReason != "core_cp" and payload.get("event_rules"):
            var_intExtras = sum(
                1
                for item in state["ledger"]
                if item["round"] == state["round"]
                and item["player"] == var_strPlayer
                and int(item["delta"]) > 0
                and item["reason"] != "core_cp"
            )
            if var_intExtras >= 1:
                state["warnings"].append("extra_cp_cap")
        _change_cp(
            state,
            var_strPlayer,
            var_intDelta,
            var_strReason,
            bool(payload.get("override")),
            event,
            None,
        )
        return
    if kind == "stratagem_used":
        _stratagem(state, event)
        return
    if kind == "objective_set":
        label = str(payload.get("objective_label") or "")[:50]
        row = {
            "round": state["round"],
            "player_turn": payload.get("player_turn") or state["player"],
            "objective_label": label,
            "controller": payload.get("controller") or "none",
        }
        state["objectives"] = [
            item
            for item in state["objectives"]
            if not (
                item["round"] == row["round"]
                and item["player_turn"] == row["player_turn"]
                and item["objective_label"] == label
            )
        ]
        state["objectives"].append(row)
        return
    if kind == "vp_scored":
        state["scores"].append(
            {
                "round": state["round"],
                "player": payload.get("player") or "me",
                "kind": payload.get("kind") or "other",
                "label": str(payload.get("label") or "")[:100],
                "vp": int(payload.get("vp") or 0),
                "created_at": event["created_at"],
            }
        )
        for player in ("me", "opponent"):
            state["vp"][player] = sum(item["vp"] for item in state["scores"] if item["player"] == player)
        return
    if kind == "shadow_set":
        var_boolLegacy = "whole_board" in payload or "objectives_controlled" in payload
        var_strPhase = str(payload.get("phase") or ("command" if var_boolLegacy else state["phase"]))
        var_strTurn = str(payload.get("turn_player") or state["player"])
        var_boolNml = bool(payload.get("nml_in_shadow"))
        var_boolOpp = bool(payload.get("opp_dz_in_shadow"))
        if var_boolLegacy and payload.get("nml_in_shadow") is None and payload.get("opp_dz_in_shadow") is None:
            var_boolNml = bool(payload.get("whole_board"))
            var_boolOpp = bool(payload.get("whole_board"))
            state["warnings"].append("shadow_legacy")
        else:
            if payload.get("nml_total") is not None and payload.get("nml_controlled") is not None:
                var_intTotal = int(payload["nml_total"])
                var_intCtrl = int(payload["nml_controlled"])
                var_boolNml = var_intTotal > 0 and var_intCtrl * 2 >= var_intTotal
            if payload.get("opp_dz_total") is not None and payload.get("opp_dz_controlled") is not None:
                var_intTotal = int(payload["opp_dz_total"])
                var_intCtrl = int(payload["opp_dz_controlled"])
                var_boolOpp = var_intTotal > 0 and var_intCtrl * 2 >= var_intTotal
        row = {
            "round": state["round"],
            "player": payload.get("player") or "me",
            "turn_player": var_strTurn,
            "phase": var_strPhase,
            "state_key": "shadow_of_chaos",
            "nml_in_shadow": var_boolNml,
            "opp_dz_in_shadow": var_boolOpp,
            "objectives_controlled": payload.get("objectives_controlled"),
            "whole_board": payload.get("whole_board"),
            "value": payload.get("value") or {},
        }
        state["shadow"] = [
            item
            for item in state["shadow"]
            if not (
                item["round"] == row["round"]
                and item.get("turn_player") == var_strTurn
                and item.get("phase") == var_strPhase
            )
        ]
        state["shadow"].append(row)
        return
    if kind == "battleshock_result":
        unit = state["live"].get(int(payload["list_unit_id"]))
        passed = bool(payload.get("passed"))
        if unit is not None:
            unit["battle_shocked"] = not passed
        state["battle_shock"].append(
            {
                "list_unit_id": payload.get("list_unit_id"),
                "passed": passed,
                "round": state["round"],
                "player": state["player"],
            }
        )
        return
    if kind == "effect_chosen":
        _choose(state, payload)
        return
    if kind == "game_ended":
        state["status"] = payload.get("status") or "finished"
        if payload.get("result") in {"win", "loss", "draw"}:
            state["result"] = payload["result"]
        if payload.get("list_label"):
            state["list_label"] = str(payload["list_label"])[:200]


def _choose(state: dict, payload: dict) -> None:
    scope = payload.get("scope") if payload.get("scope") in CHOICE_SCOPES else "turn"
    options = [str(item)[:200] for item in (payload.get("options") or [])][:12]
    count = payload.get("count")
    if count and len(options) > int(count):
        state["warnings"].append("choice_over_count")
    row = {
        "effect_id": payload.get("effect_id"),
        "list_unit_id": payload.get("list_unit_id"),
        "options": options,
        "scope": scope,
        "round": state["round"],
        "player": payload.get("player") or state["player"],
        "phase": state["phase"],
    }
    state["choices"] = [item for item in state["choices"] if not _same_choice(item, row)]
    state["choices"].append(row)


def _same_choice(left: dict, right: dict) -> bool:
    if left["effect_id"] != right["effect_id"] or left["list_unit_id"] != right["list_unit_id"]:
        return False
    if right["scope"] == "battle":
        return True
    if right["scope"] == "round":
        return left["round"] == right["round"]
    return left["round"] == right["round"] and left["player"] == right["player"]


def _change_cp(state, player, delta, reason, override, event, stratagem_use_id) -> bool:
    if player not in state["cp"] or state["cp"][player] is None:
        state["cp"][player] = 0
    current = int(state["cp"][player])
    nxt = current + int(delta)
    applied = int(delta)
    if nxt < 0 and not override:
        state["warnings"].append("cp_blocked")
        return False
    if nxt < 0 and override:
        applied = -current
        nxt = 0
        state["warnings"].append("cp_clamped")
    if nxt > 99:
        applied = 99 - current
        nxt = 99
    state["cp"][player] = nxt
    if applied != 0:
        state["ledger"].append(
            {
                "id": str(uuid.uuid5(uuid.UUID(event["id"]), reason)),
                "round": state["round"],
                "player": player,
                "phase": state["phase"],
                "delta": applied,
                "reason": reason,
                "stratagem_use_id": stratagem_use_id,
                "created_at": event["created_at"],
            }
        )
    return True


def _limit_hit(state: dict, name: str, player: str, limit: str) -> bool:
    rows = [
        item
        for item in state["stratagem_uses"]
        if item["stratagem_name"] == name and item["player"] == player
    ]
    if limit == "per_battle":
        return bool(rows)
    if limit == "per_round":
        return any(item["round"] == state["round"] for item in rows)
    if limit == "per_turn":
        return any(item["round"] == state["round"] for item in rows)
    if limit == "per_phase":
        return any(
            item["round"] == state["round"] and item["phase"] == state["phase"] for item in rows
        )
    return False


def _stratagem(state: dict, event: dict) -> None:
    payload = event["payload"]
    name = payload.get("stratagem_name") or "Stratagem"
    player = payload.get("player") or state["player"]
    limit = payload.get("use_limit") or "none"
    if limit != "none" and _limit_hit(state, name, player, limit) and not payload.get("limit_overridden"):
        state["warnings"].append("stratagem_limit")
        return
    use_id = str(uuid.uuid5(uuid.UUID(event["id"]), "stratagem"))
    spent = int(payload.get("cp_spent") or 0)
    if spent and not _change_cp(
        state,
        player,
        -spent,
        "stratagem",
        bool(payload.get("cp_override")),
        event,
        use_id,
    ):
        return
    state["stratagem_uses"].append(
        {
            "id": use_id,
            "ability_id": payload.get("ability_id"),
            "stratagem_name": name,
            "round": state["round"],
            "player": player,
            "phase": state["phase"],
            "cp_spent": spent if state["cp"][player] is not None else 0,
            "target_list_unit_id": payload.get("target_list_unit_id"),
            "limit_overridden": bool(payload.get("limit_overridden")),
            "created_at": event["created_at"],
        }
    )
