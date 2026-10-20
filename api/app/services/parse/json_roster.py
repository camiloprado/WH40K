from __future__ import annotations

import math
import re

from app.services.parse.leaders import pair_leaders
from app.services.parse.models import (
    DetachmentHeader,
    ParseResult,
    ParseWarning,
    ParsedModel,
    ParsedUnit,
    ParsedWargear,
    WeaponStats,
    LeadingRef,
)
from app.services.parse.text_parser import _enhancement_sums

MAX_NODES = 5000
MAX_DEPTH = 20
MAX_STR = 500
MAX_ABS_INT = 10**7
DICE_RE = re.compile(r"^(?:\d{1,2}|D3|D6|\d?D[36](?:\+\d{1,2})?)$")
LEADING_RE = re.compile(r"^Leading\s+(.{1,200}?)(?:\[(\d{1,3})\])?$", re.IGNORECASE)
STRUCTURAL = {
    "detachment",
    "warlord",
    "enhancement",
    "configuration",
    "upgrade",
    "attachment",
    "prime",
}
SKIP_FORCE = {"show/hide options"}
BATTLE_SIZE_RE = re.compile(r"^(?P<name>.{1,80}?)\s*\(\s*(?P<points>\d{2,6})\s+points?\s+limits?\)\s*$", re.IGNORECASE)
WEAPON_TYPES = {"ranged weapons", "melee weapons"}
ABILITY_TYPES = {"abilities", "psychic abilities"}
FNP_RE = re.compile(r"feel no pain\s+([2-6])\+", re.IGNORECASE)
SKIP_ABILITY = {"leader"}


def parse_json(payload: dict) -> ParseResult:
    result = ParseResult(format="nr_json")
    counter = [0]
    cleaned = _sanitize(payload, 0, counter, result, "$")
    if not isinstance(cleaned, dict):
        result.warnings.append(ParseWarning(json_path="$", reason="json_invalid"))
        return result
    roster = cleaned.get("roster") if isinstance(cleaned.get("roster"), dict) else cleaned
    if not isinstance(roster, dict):
        result.warnings.append(ParseWarning(json_path="$", reason="json_invalid"))
        return result
    gen = roster.get("generator") or roster.get("generatedBy")
    if isinstance(gen, str):
        result.generator = gen[:120]
    system = roster.get("gameSystemName")
    if isinstance(system, str) and system.strip() and "40" not in system:
        result.warnings.append(ParseWarning(reason="game_system", text=system.strip()[:80]))
    roster_name = str(roster.get("name") or "").strip()
    if roster_name and roster_name.casefold() not in {"army roster", "roster"}:
        result.header.list_name = roster_name[:200]
    _apply_roster_costs(roster, result)
    forces = roster.get("forces") if isinstance(roster.get("forces"), list) else []
    for fi, force in enumerate(forces):
        if not isinstance(force, dict):
            continue
        faction = force.get("catalogueName") or force.get("name")
        if isinstance(faction, str) and not result.header.faction_name:
            result.header.faction_name = faction[:200]
        selections = force.get("selections") if isinstance(force.get("selections"), list) else []
        for si, sel in enumerate(selections):
            _consume(
                sel,
                f"$.forces[{fi}].selections[{si}]",
                result,
                parent="force",
            )
    if not result.header.faction_name:
        result.warnings.append(ParseWarning(reason="faction_missing"))
    _enhancement_sums(result)
    pair_leaders(result)
    return result


def _sanitize(node, depth: int, counter: list[int], result: ParseResult, path: str):
    if depth > MAX_DEPTH:
        result.warnings.append(ParseWarning(json_path=path, reason="max_depth"))
        return None
    if isinstance(node, dict):
        counter[0] += 1
        if counter[0] > MAX_NODES:
            result.warnings.append(ParseWarning(json_path=path, reason="too_many_nodes"))
            return None
        cleaned: dict = {}
        for key, value in node.items():
            if key == "description":
                continue
            if key == "characteristics" and isinstance(value, list):
                value = [item for item in value if not (isinstance(item, dict) and str(item.get("name") or "").lower() == "description")]
            child = _sanitize(value, depth + 1, counter, result, f"{path}.{key}")
            if child is not None:
                cleaned[key] = child
        return cleaned
    if isinstance(node, list):
        out = []
        for index, item in enumerate(node):
            child = _sanitize(item, depth + 1, counter, result, f"{path}[{index}]")
            if child is not None:
                out.append(child)
        return out
    if isinstance(node, str):
        if len(node) > MAX_STR:
            result.warnings.append(ParseWarning(json_path=path, reason="truncated", text=node[:80]))
            return node[:MAX_STR]
        return node
    if isinstance(node, bool) or node is None:
        return node
    if isinstance(node, int):
        if abs(node) > MAX_ABS_INT:
            result.warnings.append(ParseWarning(json_path=path, reason="number_out_of_range"))
            return None
        return node
    if isinstance(node, float):
        if not math.isfinite(node) or abs(node) > MAX_ABS_INT:
            result.warnings.append(ParseWarning(json_path=path, reason="number_out_of_range"))
            return None
        return node
    return None


def _apply_roster_costs(roster: dict, result: ParseResult) -> None:
    total = _sum_pts(roster.get("costs"))
    if total is not None:
        result.header.total_points_declared = total
    limit = _sum_pts(roster.get("costLimits"))
    if limit is not None:
        result.header.points_limit = limit


def _sum_pts(costs) -> int | None:
    if not isinstance(costs, list):
        return None
    found = False
    total = 0
    for cost in costs:
        if not isinstance(cost, dict):
            continue
        name = str(cost.get("name") or "").lower()
        if name not in {"pts", "points", "pt"}:
            continue
        value = cost.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        total += int(value)
        found = True
    if not found:
        return None
    return max(0, min(total, 100000))


def _categories(node: dict) -> list[str]:
    raw = node.get("categories")
    names: list[str] = []
    if not isinstance(raw, list):
        return names
    for item in raw:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names


def _consume(node, path: str, result: ParseResult, parent: str) -> None:
    if not isinstance(node, dict):
        return
    typ = str(node.get("type") or "").lower()
    cats = {c.casefold() for c in _categories(node)}
    name = str(node.get("name") or "").strip()
    children = node.get("selections") if isinstance(node.get("selections"), list) else []
    folded = name.casefold()
    if parent == "force" and folded == "battle size":
        for child in children:
            if isinstance(child, dict):
                _battle_size(str(child.get("name") or ""), result)
                break
        return
    if parent == "force" and folded in SKIP_FORCE:
        return
    if parent == "force" and folded == "force disposition":
        for child in children:
            child_name = str(child.get("name") or "").strip() if isinstance(child, dict) else ""
            if child_name:
                result.header.force_disposition = child_name[:200]
                break
        return
    if parent == "force" and _is_detachment(name, cats, children):
        for item in _detachment_names(name, children):
            result.header.detachments.append(item)
        return
    is_roster_unit = typ == "unit" or (
        parent == "force" and typ == "model" and _sum_pts(node.get("costs")) is not None
    )
    if is_roster_unit or (parent == "force" and typ == "" and _sum_pts(node.get("costs")) is not None):
        if typ == "":
            result.warnings.append(ParseWarning(json_path=path, reason="type_missing", text=name[:80]))
        result.units.append(_unit_from(node, path, result))
        return
    for index, child in enumerate(children):
        _consume(child, f"{path}.selections[{index}]", result, parent)


def _battle_size(label: str, result: ParseResult) -> None:
    label = label.strip()
    if not label:
        return
    match = BATTLE_SIZE_RE.match(label)
    result.header.battle_size = (match.group("name") if match else label)[:80]
    if result.header.points_limit is None and match:
        result.header.points_limit = int(match.group("points"))


def _is_detachment(name: str, cats: set[str], children: list) -> bool:
    if "detachment" in cats or name.casefold() == "detachment":
        return True
    return any(isinstance(child, dict) and str(child.get("group") or "").casefold() == "detachment" for child in children)


def _detachment_names(name: str, children: list) -> list[DetachmentHeader]:
    labels = []
    for child in children:
        if not isinstance(child, dict):
            continue
        child_name = str(child.get("name") or "").strip()
        if child_name and child_name.casefold() != "detachment":
            labels.append(child_name)
    if not labels and name.casefold() != "detachment":
        labels.append(name)
    out = []
    for label in labels:
        variant = None
        det_name = label
        if "(" in label and label.endswith(")"):
            det_name = label[: label.rfind("(")].strip()
            variant = label[label.rfind("(") + 1 : -1].strip() or None
        if det_name:
            out.append(DetachmentHeader(name=det_name[:200], variant=variant))
    return out


def _unit_from(node: dict, path: str, result: ParseResult) -> ParsedUnit:
    name = str(node.get("name") or "Unnamed").strip()[:200]
    export_ref = None
    custom = node.get("customName")
    if isinstance(custom, str) and re.fullmatch(r"Char\d{1,3}", custom.strip()):
        export_ref = custom.strip()
    children = node.get("selections") if isinstance(node.get("selections"), list) else []
    model_count = _model_count(node, children)
    points = _sum_pts(node.get("costs")) or 0
    cats = _categories(node)
    cat_cf = {c.casefold() for c in cats}
    keywords = [c[:40] for c in cats if c.casefold() not in STRUCTURAL and len(c) <= 40 and "." not in c]
    nr_id = str(node["id"]) if isinstance(node.get("id"), str) else None
    unit = ParsedUnit(
        json_path=path,
        export_ref=export_ref,
        nr_id=nr_id,
        name=name,
        model_count=model_count,
        points=min(points, 10000),
        is_warlord=_is_warlord(node, children),
        is_character="character" in cat_cf or bool(export_ref),
        keywords=keywords[:50],
        leading=_leading_from(node),
        **_sheet(node),
        ability_names=_ability_names(node),
    )
    for index, child in enumerate(children):
        _absorb_child(child, f"{path}.selections[{index}]", unit, result)
    if unit.is_warlord:
        result.header.warlord_name = result.header.warlord_name or unit.name
        result.header.warlord_ref = result.header.warlord_ref or unit.export_ref
    return unit


def _sheet(node: dict) -> dict:
    chars: dict[str, str] = {}
    for profile in node.get("profiles") or []:
        if not isinstance(profile, dict) or str(profile.get("typeName") or "").lower() != "unit":
            continue
        for item in profile.get("characteristics") or []:
            if not isinstance(item, dict):
                continue
            value = item.get("$text") if isinstance(item.get("$text"), str) else item.get("value")
            if isinstance(value, str):
                chars[str(item.get("name") or "").lower()] = value
    base = chars.get("base", "").strip()
    return {
        "movement": _small(chars.get("m"), 0, 99),
        "toughness": _small(chars.get("t"), 1, 99),
        "save": _small(chars.get("sv"), 2, 6),
        "wounds": _small(chars.get("w"), 1, 99),
        "leadership": _small(chars.get("ld"), 0, 12),
        "oc": _small(chars.get("oc"), 0, 99),
        "invuln": _small(chars.get("insv"), 2, 6),
        "fnp": _fnp(node),
        "base_size_mm": base[:40] or None,
    }


def _fnp(node: dict) -> int | None:
    for rule in node.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        match = FNP_RE.search(str(rule.get("name") or ""))
        if match:
            return int(match.group(1))
    return None


def _ability_names(node: dict) -> list[str]:
    names: list[str] = []
    for profile in node.get("profiles") or []:
        if not isinstance(profile, dict) or str(profile.get("typeName") or "").lower() not in ABILITY_TYPES:
            continue
        name = str(profile.get("name") or "").strip()
        folded = name.casefold()
        if not name or folded in SKIP_ABILITY or folded.startswith("invulnerable save"):
            continue
        if name not in names:
            names.append(name[:200])
    return names[:30]


def _model_count(node: dict, children: list) -> int:
    nested = 0
    found = False
    for child in children:
        if not isinstance(child, dict) or str(child.get("type") or "").lower() != "model":
            continue
        found = True
        nested += _number(child.get("number"), 1)
    if found:
        return min(max(nested, 1), 200)
    return min(max(_number(node.get("number"), 1), 1), 200)


def _number(value, default: int = 1) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _is_warlord(node: dict, children: list) -> bool:
    if "warlord" in {c.casefold() for c in _categories(node)}:
        return True
    for child in children:
        if not isinstance(child, dict):
            continue
        if str(child.get("name") or "").casefold() == "warlord":
            return True
        if "warlord" in {c.casefold() for c in _categories(child)}:
            return True
    return False


def _leading_from(node: dict) -> list[LeadingRef]:
    refs: list[LeadingRef] = []
    for item in node.get("associations") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").lower() != "outgoing":
            continue
        if "lead" not in str(item.get("name") or "").casefold():
            continue
        target = item.get("to")
        if isinstance(target, str) and target:
            refs.append(LeadingRef(name=str(item.get("name") or "Leading")[:200], target_id=target))
    return refs


def _is_enhancement(node: dict) -> bool:
    if "enhancement" in {c.casefold() for c in _categories(node)}:
        return True
    if str(node.get("group") or "").casefold() == "enhancements":
        return True
    for cost in node.get("costs") or []:
        if isinstance(cost, dict) and str(cost.get("name") or "").casefold() == "enhancements":
            return True
    return False


def _absorb_child(node, path: str, unit: ParsedUnit, result: ParseResult) -> None:
    if not isinstance(node, dict):
        return
    typ = str(node.get("type") or "").lower()
    name = str(node.get("name") or "").strip()
    cats = {c.casefold() for c in _categories(node)}
    if LEADING_RE.match(name) or "attachment" in cats:
        match = LEADING_RE.match(name)
        if match:
            index = int(match.group(2)) if match.group(2) else None
            unit.leading.append(LeadingRef(name=match.group(1).strip(), index=index))
        elif name:
            unit.leading.append(LeadingRef(name=name[:200]))
        return
    if _is_enhancement(node):
        unit.enhancement_name = name[:200]
        unit.enhancement_points = _sum_pts(node.get("costs")) or 0
        return
    if name.casefold() == "warlord" or "warlord" in cats:
        unit.is_warlord = True
        return
    if typ == "model":
        model = ParsedModel(
            name=name[:200] or unit.name,
            count=min(max(_number(node.get("number"), 1), 1), 200),
        )
        children = node.get("selections") if isinstance(node.get("selections"), list) else []
        for child in children:
            _absorb_wargear(child, model.wargear, unit)
        unit.models.append(model)
        return
    _absorb_wargear(node, unit.wargear, unit)


def _absorb_wargear(node, bucket: list[ParsedWargear], unit: ParsedUnit) -> None:
    if not isinstance(node, dict):
        return
    name = _weapon_name(node.get("name"))
    if not name or LEADING_RE.match(name):
        return
    if _is_enhancement(node):
        unit.enhancement_name = name[:200]
        unit.enhancement_points = _sum_pts(node.get("costs")) or 0
        return
    weapons = _weapon_profiles(node)
    count = min(max(_number(node.get("number"), 1), 1), 200)
    if not weapons:
        bucket.append(ParsedWargear(name=name[:200], count=count))
        return
    for profile in weapons:
        stats = _profile_stats(profile)
        bucket.append(
            ParsedWargear(
                name=_weapon_name(profile.get("name")) or name,
                count=count,
                stats=stats,
            )
        )


def _weapon_name(raw) -> str:
    return str(raw or "").replace("➤", "").strip()[:200]


def _weapon_profiles(node: dict) -> list[dict]:
    out = []
    for profile in node.get("profiles") or []:
        if isinstance(profile, dict) and str(profile.get("typeName") or "").lower() in WEAPON_TYPES:
            out.append(profile)
    return out


def _profile_stats(profile: dict) -> WeaponStats | None:
    chars: dict[str, str] = {}
    raw = profile.get("characteristics")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = str(item.get("name") or "").lower()
            value = item.get("value")
            if not isinstance(value, str):
                value = item.get("$text")
            if isinstance(value, str):
                chars[key] = value
    type_name = str(profile.get("typeName") or "").lower()
    kind = "unknown"
    if "melee" in type_name:
        kind = "melee"
    elif "ranged" in type_name:
        kind = "ranged"
    keywords: list[str] = []
    kw = chars.get("keywords") or ""
    if kw and len(kw) <= 200 and "." not in kw:
        keywords = [part.strip()[:40] for part in kw.split(",") if part.strip() and len(part.strip()) <= 40]
    return WeaponStats(
        kind=kind,  # type: ignore[arg-type]
        range_in=_range(chars.get("range")),
        attacks=_dice(chars.get("a")),
        skill=_skill(chars.get("bs") or chars.get("ws")),
        strength=_small(chars.get("s"), low=1, high=30),
        ap=_small(chars.get("ap"), low=-6, high=0),
        damage=_dice(chars.get("d")),
        keywords=keywords[:50],
    )


def _dice(value: str | None) -> str | None:
    if not value:
        return None
    token = value.strip().upper().replace(" ", "")
    if DICE_RE.match(token):
        return token
    return None


def _range(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\d{1,3})", value)
    if not match or "melee" in value.lower():
        return None
    number = int(match.group(1))
    if number > 200:
        return None
    return number


def _skill(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"([2-6])", value)
    if not match:
        return None
    return int(match.group(1))


def _small(value: str | None, low: int, high: int) -> int | None:
    if not value:
        return None
    match = re.search(r"-?\d{1,2}", value)
    if not match:
        return None
    number = int(match.group(0))
    if number < low or number > high:
        return None
    return number
