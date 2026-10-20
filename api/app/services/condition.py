from __future__ import annotations

PHASES = {
    "deployment",
    "round_start",
    "command",
    "battle_shock",
    "movement",
    "shooting",
    "charge",
    "fight",
    "end_of_turn",
    "any",
}
STATE_FIELDS = {
    "moved",
    "shot",
    "charged",
    "fought",
    "engaged",
    "on_action",
    "battle_shocked",
    "destroyed",
    "in_reserves",
    "below_half",
}
FACT_KEYS = {
    "phase",
    "turn_owner",
    "unit_keyword",
    "weapon_keyword",
    "is_leading",
    "game.shadow_of_chaos",
    "game.round",
}


class ConditionError(ValueError):
    pass


def validate_condition(node: object, depth: int = 1, counter: list[int] | None = None) -> None:
    if node in (None, {}):
        return
    if counter is None:
        counter = [0]
    if not isinstance(node, dict):
        raise ConditionError("condition_json precisa ser objeto")
    counter[0] += 1
    if depth > 5 or counter[0] > 20:
        raise ConditionError("condition_json excede o limite")
    if "all" in node or "any" in node:
        key = "all" if "all" in node else "any"
        if len(node) != 1 or not isinstance(node[key], list) or not node[key]:
            raise ConditionError("combinador inválido")
        for child in node[key]:
            validate_condition(child, depth + 1, counter)
        return
    if "not" in node:
        if len(node) != 1:
            raise ConditionError("not inválido")
        validate_condition(node["not"], depth + 1, counter)
        return
    if len(node) != 1:
        raise ConditionError("fato inválido")
    key, value = next(iter(node.items()))
    if key.startswith("state."):
        field = key.split(".", 1)[1]
        if field not in STATE_FIELDS:
            raise ConditionError("estado desconhecido")
        return
    if key not in FACT_KEYS:
        raise ConditionError("fato desconhecido")
    if key == "phase" and value not in PHASES:
        raise ConditionError("fase inválida")


def matches(node: object, facts: dict) -> bool:
    if node in (None, {}):
        return True
    if not isinstance(node, dict):
        return False
    if "all" in node:
        return all(matches(child, facts) for child in node["all"])
    if "any" in node:
        return any(matches(child, facts) for child in node["any"])
    if "not" in node:
        return not matches(node["not"], facts)
    key, expected = next(iter(node.items()))
    if key.startswith("state."):
        return facts.get("state", {}).get(key.split(".", 1)[1]) == expected
    if key == "unit_keyword":
        return expected in facts.get("unit_keywords", [])
    if key == "weapon_keyword":
        return expected in facts.get("weapon_keywords", [])
    if key == "game.shadow_of_chaos":
        return bool(facts.get("shadow")) == bool(expected)
    if key == "game.round":
        return facts.get("round") == expected
    return facts.get(key) == expected
