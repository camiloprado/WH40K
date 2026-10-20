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
        var_lstContested = [item for item in var_lstAreas if item in ("nml", "opp_dz")]
        if var_objExpected is True:
            return bool(var_lstContested)
        if var_objExpected is False:
            return not var_lstContested
        return str(var_objExpected) in var_lstAreas
    if var_strKey == "game.round":
        return facts.get("round") == var_objExpected
    if var_strKey == "turn_owner":
        if var_objExpected == "both":
            return True
        return facts.get("turn_owner") == var_objExpected
    if var_strKey == "is_leading":
        return bool(facts.get("is_leading")) == bool(var_objExpected)
    if var_strKey == "phase":
        if var_objExpected == "any":
            return True
        return facts.get("phase") == var_objExpected
    if var_strKey in con_setFactKeys or var_strKey.startswith("state."):
        return facts.get(var_strKey) == var_objExpected
    return False


def _shadow_unevaluable(expected: object, facts: dict) -> bool:
    """Sem mapa completo da Shadow, nml/opp_dz e o booleano True/False não são decidíveis (R1)."""
    if facts.get("shadow_areas_complete"):
        return False
    if expected is True or expected is False:
        return True
    var_strArea = str(expected)
    if var_strArea in ("nml", "opp_dz"):
        return var_strArea not in list(facts.get("shadow_areas") or [])
    return False


def condition_unevaluable(node: object, facts: dict) -> bool:
    """Fato que o guia/lembrete não consegue avaliar (não filtra; selo condicional)."""
    if node in (None, {}):
        return False
    if not isinstance(node, dict):
        return False
    if "all" in node:
        return any(condition_unevaluable(child, facts) for child in node["all"])
    if "any" in node:
        return any(condition_unevaluable(child, facts) for child in node["any"])
    if "not" in node:
        return condition_unevaluable(node["not"], facts)
    var_strKey, var_objExpected = next(iter(node.items()))
    if var_strKey == "game.shadow_of_chaos":
        return _shadow_unevaluable(var_objExpected, facts)
    if var_strKey.startswith("state.") and "state" not in facts:
        return True
    if var_strKey in ("unit_keyword", "weapon_keyword", "is_leading", "game.round") and var_strKey.split(".")[-1] not in facts and var_strKey not in facts:
        if var_strKey == "unit_keyword" and "unit_keywords" not in facts:
            return True
        if var_strKey == "weapon_keyword" and "weapon_keywords" not in facts:
            return True
        if var_strKey == "is_leading" and "is_leading" not in facts:
            return True
        if var_strKey == "game.round" and "round" not in facts:
            return True
    return False


def guide_match(node: object, facts: dict) -> tuple[bool, bool]:
    """Guia/lembrete: (incluir, condicional). Motor allow/deny continua em matches() (M6)."""
    if node in (None, {}):
        return True, False
    if matches(node, facts):
        return True, False
    if condition_unevaluable(node, facts):
        return True, True
    return False, False


def condition_label(node: object) -> str:
    if node in (None, {}):
        return ""
    if not isinstance(node, dict):
        return str(node)
    if "all" in node:
        return " e ".join(condition_label(child) for child in node["all"])
    if "any" in node:
        return " ou ".join(condition_label(child) for child in node["any"])
    if "not" in node:
        return f"não ({condition_label(node['not'])})"
    var_strKey, var_objExpected = next(iter(node.items()))
    if var_strKey == "game.shadow_of_chaos":
        if var_objExpected is True:
            return "Shadow ativo (TdN ou DZ do oponente)"
        if var_objExpected is False:
            return "Shadow só na própria DZ"
        return f"Shadow: {var_objExpected}"
    return f"{var_strKey}={var_objExpected}"
