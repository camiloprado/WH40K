from __future__ import annotations

con_setPhases = {
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
con_setStateFields = {
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
con_setFactKeys = {
    "phase",
    "turn_owner",
    "unit_keyword",
    "weapon_keyword",
    "is_leading",
    "game.shadow_of_chaos",
    "game.round",
}

# Compatibilidade com imports existentes (contrato público do módulo).
PHASES = con_setPhases
STATE_FIELDS = con_setStateFields
FACT_KEYS = con_setFactKeys


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
    var_intDepth = depth
    if var_intDepth > 5 or counter[0] > 20:
        raise ConditionError("condition_json excede o limite")
    if "all" in node or "any" in node:
        var_strKey = "all" if "all" in node else "any"
        if len(node) != 1 or not isinstance(node[var_strKey], list) or not node[var_strKey]:
            raise ConditionError("combinador inválido")
        for var_objChild in node[var_strKey]:
            validate_condition(var_objChild, var_intDepth + 1, counter)
        return
    if "not" in node:
        if len(node) != 1:
            raise ConditionError("not inválido")
        validate_condition(node["not"], var_intDepth + 1, counter)
        return
    if len(node) != 1:
        raise ConditionError("fato inválido")
    var_strKey, var_objValue = next(iter(node.items()))
    if var_strKey.startswith("state."):
        var_strField = var_strKey.split(".", 1)[1]
        if var_strField not in con_setStateFields:
            raise ConditionError("estado desconhecido")
        return
    if var_strKey not in con_setFactKeys:
        raise ConditionError("fato desconhecido")
    if var_strKey == "phase" and var_objValue not in con_setPhases:
        raise ConditionError("fase inválida")


def matches(node: object, facts: dict) -> bool:
    if node in (None, {}):
        return True
    if not isinstance(node, dict):
        return False
    if "all" in node:
        return all(matches(var_objChild, facts) for var_objChild in node["all"])
    if "any" in node:
        return any(matches(var_objChild, facts) for var_objChild in node["any"])
    if "not" in node:
        return not matches(node["not"], facts)
    var_strKey, var_objExpected = next(iter(node.items()))
    if var_strKey.startswith("state."):
        return facts.get("state", {}).get(var_strKey.split(".", 1)[1]) == var_objExpected
    if var_strKey == "unit_keyword":
        return var_objExpected in facts.get("unit_keywords", [])
    if var_strKey == "weapon_keyword":
        return var_objExpected in facts.get("weapon_keywords", [])
    if var_strKey == "game.shadow_of_chaos":
        var_lstAreas = list(facts.get("shadow_areas") or [])
        if not var_lstAreas and "shadow" in facts and not isinstance(facts.get("shadow"), list):
            if var_objExpected is True:
                return bool(facts.get("shadow"))
            if var_objExpected is False:
                return not bool(facts.get("shadow"))
            return False
        if var_objExpected is True:
            return bool(var_lstAreas)
        if var_objExpected is False:
            return not var_lstAreas
        return str(var_objExpected) in var_lstAreas
    if var_strKey == "game.round":
        return facts.get("round") == var_objExpected
    if var_strKey == "turn_owner":
        return facts.get("turn_owner") == var_objExpected
    if var_strKey == "is_leading":
        return bool(facts.get("is_leading")) == bool(var_objExpected)
    if var_strKey in con_setFactKeys or var_strKey.startswith("state."):
        return facts.get(var_strKey) == var_objExpected
    return False
