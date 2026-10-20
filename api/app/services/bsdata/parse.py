"""Lê catálogos BattleScribe em JSON (BSData) e extrai só a estrutura.

Os textos de regra servem para deduzir fase, momento e escolhas e são descartados aqui:
nada do que sai deste módulo carrega descrição da GW.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterator

PHASE_RE = re.compile(
    r"\b(?P<owner>your opponent's|your|each player's|either player's|the|each|a|any)?\s*"
    r"(?P<phase>Command|Movement|Shooting|Charge|Fight) phase",
    re.IGNORECASE,
)
TIMING_RE = re.compile(r"\b(?P<when>start|end) of (?:your |the |each |either player's |your opponent's |each player's )?(?:\w+ )?phase", re.IGNORECASE)
END_TURN_RE = re.compile(r"\bend of (?:your|the|each|your opponent's|either player's) turn\b", re.IGNORECASE)
DEPLOY_RE = re.compile(r"\b(Declare Battle Formations|deploy(?:ment|ed)?|Redeploy|start of the battle)\b", re.IGNORECASE)
CHOICE_RE = re.compile(r"\b(?:select|choose)\s+(?:up to\s+)?(?P<count>one|two|three|four|\d)\b", re.IGNORECASE)
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4}
DICE_RE = re.compile(r"^(\d{1,2}|D3|D6|\d?D[36](\+\d{1,2})?)$")
SKIP_LINKS = {"enhancements", "crusade", "warlord", "detachment", "show/hide options", "order of battle"}
SKIP_ABILITIES = {"leader"}
WEAPON_TYPES = {"Ranged Weapons": "ranged", "Melee Weapons": "melee"}
MAX_DEPTH = 8


@dataclass
class Guess:
    phase: str
    turn_owner: str
    timing: str


@dataclass
class ParsedAbility:
    name: str
    ref: str
    guess: Guess | None = None
    options: list[str] = field(default_factory=list)
    count: int | None = None
    scope: str = "turn"


@dataclass
class ParsedUnit:
    name: str
    ref: str
    keywords: list[str]
    stats: dict[str, int | None]
    is_character: bool
    weapons: list[dict]
    abilities: list[ParsedAbility]


@dataclass
class ParsedEnhancement:
    name: str
    ref: str
    points: int | None
    ability: ParsedAbility


@dataclass
class ParsedDetachment:
    name: str
    ref: str
    rules: list[ParsedAbility]
    enhancements: list[ParsedEnhancement] = field(default_factory=list)


@dataclass
class ParsedFaction:
    catalogue: str
    revision: int | None
    units: list[ParsedUnit]
    detachments: list[ParsedDetachment]
    faction_rules: list[ParsedAbility]


def guess_effect(text: str) -> Guess | None:
    if not text:
        return None
    match = PHASE_RE.search(text)
    timing_match = TIMING_RE.search(text)
    timing = timing_match.group("when").lower() if timing_match else "during"
    if match:
        owner_word = (match.group("owner") or "").lower()
        if owner_word == "your opponent's":
            owner = "opponent"
        elif owner_word in {"each player's", "either player's", "each", "any"}:
            owner = "both"
        else:
            owner = "own"
        if re.search(r"\b(either player's|each player's|your opponent's)\b", text, re.IGNORECASE) and owner == "own":
            owner = "both" if re.search(r"\byour (Command|Movement|Shooting|Charge|Fight) phase", text, re.IGNORECASE) else owner
        return Guess(phase=match.group("phase").lower(), turn_owner=owner, timing=timing)
    if END_TURN_RE.search(text):
        owner = "both" if re.search(r"\b(each|either player's|the) turn\b", text, re.IGNORECASE) else "own"
        return Guess(phase="end_of_turn", turn_owner=owner, timing="end")
    if DEPLOY_RE.search(text):
        return Guess(phase="deployment", turn_owner="both", timing="during")
    return None


def choice_count(text: str) -> int | None:
    match = CHOICE_RE.search(text or "")
    if not match:
        return None
    raw = match.group("count").lower()
    return WORDS.get(raw) or int(raw)


def _text(node: dict) -> str:
    for item in node.get("characteristics") or []:
        if item.get("name") == "Description":
            return str(item.get("$text") or "")
    value = node.get("description")
    if isinstance(value, dict):
        return str(value.get("$text") or "")
    return str(value or "")


def _chars(profile: dict) -> dict[str, str]:
    return {str(item.get("name")): str(item.get("$text") or "").strip() for item in profile.get("characteristics") or []}


def _int(value: str | None, low: int | None = None, high: int | None = None) -> int | None:
    match = re.search(r"-?\d+", value or "")
    if not match:
        return None
    number = int(match.group())
    if (low is not None and number < low) or (high is not None and number > high):
        return None
    return number


def _dice(value: str | None) -> str | None:
    text = (value or "").strip().upper()
    return text if DICE_RE.match(text) else None


def _pts(node: dict) -> int | None:
    for cost in node.get("costs") or []:
        if cost.get("name") == "pts":
            try:
                return int(float(cost.get("value") or 0)) or None
            except (TypeError, ValueError):
                return None
    return None


class Index:
    def __init__(self, catalogues: dict[str, dict]):
        self.catalogues = catalogues
        self.by_id: dict[str, tuple[dict, str]] = {}
        for name, cat in catalogues.items():
            self._walk(cat, name, 0)

    def _walk(self, node: Any, owner: str, depth: int) -> None:
        if depth > 60:
            return
        if isinstance(node, dict):
            node_id = node.get("id")
            if isinstance(node_id, str) and "targetId" not in node:
                self.by_id.setdefault(node_id, (node, owner))
            for value in node.values():
                if isinstance(value, (dict, list)):
                    self._walk(value, owner, depth + 1)
        elif isinstance(node, list):
            for value in node:
                self._walk(value, owner, depth + 1)

    def get(self, target: str | None) -> dict | None:
        found = self.by_id.get(target or "")
        return found[0] if found else None

    def owner(self, target: str | None) -> str | None:
        found = self.by_id.get(target or "")
        return found[1] if found else None


def root_entries(index: Index, catalogue: str, seen: set[str] | None = None) -> Iterator[dict]:
    seen = seen if seen is not None else set()
    if catalogue in seen or catalogue not in index.catalogues:
        return
    seen.add(catalogue)
    cat = index.catalogues[catalogue]
    for link in cat.get("entryLinks") or []:
        target = index.get(link.get("targetId"))
        if target is not None:
            yield target
    yield from cat.get("selectionEntries") or []
    for link in cat.get("catalogueLinks") or []:
        if link.get("importRootEntries"):
            linked = _catalogue_by_id(index, link.get("targetId"))
            if linked:
                yield from root_entries(index, linked, seen)


def _imported(index: Index, catalogue: str, seen: set[str]) -> set[str]:
    if catalogue in seen or catalogue not in index.catalogues:
        return seen
    seen.add(catalogue)
    for link in index.catalogues[catalogue].get("catalogueLinks") or []:
        linked = _catalogue_by_id(index, link.get("targetId"))
        if linked and (link.get("importRootEntries") or index.catalogues[linked].get("library")):
            _imported(index, linked, seen)
    return seen


def _catalogue_by_id(index: Index, catalogue_id: str | None) -> str | None:
    for name, cat in index.catalogues.items():
        if cat.get("id") == catalogue_id:
            return name
    return None


@dataclass
class _Collected:
    unit_profile: dict | None = None
    abilities: list[dict] = field(default_factory=list)
    extra_profiles: list[dict] = field(default_factory=list)
    weapons: list[dict] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    enhancement_groups: list[dict] = field(default_factory=list)


def _collect(index: Index, node: dict, out: _Collected, seen: set[str], depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        return
    node_id = node.get("id")
    if node_id and node_id in seen:
        return
    if node_id:
        seen.add(node_id)
    for profile in node.get("profiles") or []:
        _add_profile(profile, out)
    for link in node.get("infoLinks") or []:
        if link.get("type") == "profile":
            target = index.get(link.get("targetId"))
            if target:
                _add_profile(target, out)
        elif link.get("type") == "rule" and link.get("targetId"):
            out.rule_ids.append(link["targetId"])
    for key in ("selectionEntries", "selectionEntryGroups"):
        for child in node.get(key) or []:
            _collect(index, child, out, seen, depth + 1)
    for link in node.get("entryLinks") or []:
        name = str(link.get("name") or "").strip().lower()
        target = index.get(link.get("targetId"))
        if target is None:
            continue
        if name == "enhancements" or str(target.get("name") or "").lower() == "enhancements":
            out.enhancement_groups.append(target)
            continue
        if name in SKIP_LINKS or "crusade" in name:
            continue
        _collect(index, target, out, seen, depth + 1)


def _add_profile(profile: dict, out: _Collected) -> None:
    kind = profile.get("typeName")
    if kind == "Unit":
        out.unit_profile = out.unit_profile or profile
    elif kind in WEAPON_TYPES:
        out.weapons.append(profile)
    elif kind in {"Abilities", "Psychic Abilities"}:
        out.abilities.append(profile)
    elif kind:
        out.extra_profiles.append(profile)


def _ability(profile_or_rule: dict, ref: str, options_pool: list[dict]) -> ParsedAbility:
    name = str(profile_or_rule.get("name") or "").strip()[:200]
    text = _text(profile_or_rule)
    options = [str(item.get("name") or "").strip()[:200] for item in options_pool if item.get("typeName") == name]
    options = [item for item in dict.fromkeys(options) if item][:12]
    count = choice_count(text)
    if options:
        count = max(1, min(count or 1, len(options), 6))
    elif count:
        count = min(count, 6)
    return ParsedAbility(name=name, ref=ref, guess=guess_effect(text), options=options, count=count, scope=choice_scope(text))


def choice_scope(text: str) -> str:
    if re.search(r"\b(start of the (first )?battle|Declare Battle Formations|until the end of the battle)\b", text or "", re.IGNORECASE):
        return "battle"
    if re.search(r"\b(each|the) battle round\b", text or "", re.IGNORECASE):
        return "round"
    return "turn"


def _weapon(profile: dict) -> dict:
    chars = _chars(profile)
    kind = WEAPON_TYPES[profile["typeName"]]
    keywords = [item.strip().upper() for item in re.split(r",", chars.get("Keywords", "")) if item.strip() and item.strip() != "-"]
    skill_raw = chars.get("BS") or chars.get("WS")
    return {
        "name": str(profile.get("name") or "").lstrip("➤ ").strip()[:200],
        "kind": kind,
        "range_in": None if kind == "melee" else _int(chars.get("Range"), 0, 300),
        "attacks": _dice(chars.get("A")),
        "skill": _int(skill_raw, 2, 6),
        "strength": _int(chars.get("S"), 1, 99),
        "ap": _int(chars.get("AP"), -6, 0),
        "damage": _dice(chars.get("D")),
        "keywords": keywords[:50],
    }


def parse_faction(catalogues: dict[str, dict], main: str, ref_prefix: str) -> ParsedFaction:
    index = Index(catalogues)
    main_cat = catalogues[main]
    units: dict[str, ParsedUnit] = {}
    detachments: dict[str, ParsedDetachment] = {}
    detachment_rule_ids: set[str] = set()
    unit_rule_ids: list[str] = []
    enhancement_groups: dict[str, dict] = {}

    for entry in root_entries(index, main):
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        if name.lower() == "detachment":
            for detachment in _detachments(index, entry, ref_prefix):
                detachments.setdefault(detachment.name, detachment)
                detachment_rule_ids.update(item.ref.rsplit("#", 1)[-1] for item in detachment.rules)
            continue
        if entry.get("type") not in {"unit", "model"} or name in units:
            continue
        collected = _Collected()
        _collect(index, entry, collected, set())
        if collected.unit_profile is None:
            continue
        stats = _chars(collected.unit_profile)
        keywords = [str(link.get("name") or "").strip() for link in entry.get("categoryLinks") or []]
        keywords = [item for item in dict.fromkeys(keywords) if item][:50]
        invuln = None
        abilities = []
        for profile in collected.abilities:
            ability_name = str(profile.get("name") or "").strip().lower()
            if ability_name.startswith("invulnerable save"):
                invuln = invuln or _int(_text(profile), 2, 6)
                continue
            if ability_name in SKIP_ABILITIES:
                continue
            abilities.append(_ability(profile, f"{ref_prefix}#{profile.get('id')}", collected.extra_profiles))
        weapons = {}
        for profile in collected.weapons:
            weapon = _weapon(profile)
            weapons.setdefault(weapon["name"], weapon)
        units[name] = ParsedUnit(
            name=name[:200],
            ref=f"{ref_prefix}#{entry.get('id')}",
            keywords=keywords,
            stats={
                "movement": _int(stats.get("M"), 0, 99),
                "toughness": _int(stats.get("T"), 1, 99),
                "save": _int(stats.get("SV") or stats.get("Sv"), 2, 6),
                "wounds": _int(stats.get("W"), 1, 99),
                "leadership": _int(stats.get("LD") or stats.get("Ld"), 0, 12),
                "oc": _int(stats.get("OC"), 0, 99),
                "invuln": invuln,
            },
            is_character=any(item.lower() == "character" for item in keywords),
            weapons=list(weapons.values()),
            abilities=_unique(abilities),
        )
        unit_rule_ids.extend(collected.rule_ids)
        for group in collected.enhancement_groups:
            enhancement_groups.setdefault(group.get("id") or str(len(enhancement_groups)), group)

    by_detachment_id = {item.ref.rsplit("#", 1)[-1]: item for item in detachments.values()}
    by_detachment_name = {item.name.lower(): item for item in detachments.values()}
    for group in enhancement_groups.values():
        for entry in _upgrades(group, index):
            target = _enhancement_detachment(entry, by_detachment_id, by_detachment_name)
            if target is None:
                continue
            profiles = [item for item in entry.get("profiles") or [] if item.get("typeName") == "Abilities"]
            ability_source = profiles[0] if profiles else entry
            enhancement = ParsedEnhancement(
                name=str(entry.get("name") or "").strip()[:200],
                ref=f"{ref_prefix}#{entry.get('id')}",
                points=_pts(entry),
                ability=_ability({**ability_source, "name": entry.get("name")}, f"{ref_prefix}#{entry.get('id')}", []),
            )
            if all(item.name != enhancement.name for item in target.enhancements):
                target.enhancements.append(enhancement)

    own = _imported(index, main, set())
    faction_rules = []
    for rule_id in dict.fromkeys(unit_rule_ids):
        if rule_id in detachment_rule_ids:
            continue
        rule = index.get(rule_id)
        if rule is None or index.owner(rule_id) not in own:
            continue
        faction_rules.append(_ability(rule, f"{ref_prefix}#{rule_id}", []))

    revision = main_cat.get("revision")
    return ParsedFaction(
        catalogue=main,
        revision=int(revision) if str(revision or "").isdigit() else None,
        units=list(units.values()),
        detachments=list(detachments.values()),
        faction_rules=_unique(faction_rules),
    )


def _unique(items: list[ParsedAbility]) -> list[ParsedAbility]:
    seen: dict[str, ParsedAbility] = {}
    for item in items:
        if item.name and item.name not in seen:
            seen[item.name] = item
    return list(seen.values())


def _detachments(index: Index, entry: dict, ref_prefix: str) -> Iterator[ParsedDetachment]:
    for node in _upgrades(entry, index):
        if str(node.get("name") or "").lower() == "detachment":
            continue
        rules = []
        for rule in node.get("rules") or []:
            rules.append(_ability(rule, f"{ref_prefix}#{rule.get('id')}", node.get("profiles") or []))
        for link in node.get("infoLinks") or []:
            if link.get("type") != "rule":
                continue
            target = index.get(link.get("targetId"))
            if target is not None:
                rules.append(_ability(target, f"{ref_prefix}#{link.get('targetId')}", node.get("profiles") or []))
        for profile in node.get("profiles") or []:
            if profile.get("typeName") == "Abilities":
                rules.append(_ability(profile, f"{ref_prefix}#{profile.get('id')}", node.get("profiles") or []))
        yield ParsedDetachment(
            name=str(node.get("name") or "").strip()[:200],
            ref=f"{ref_prefix}#{node.get('id')}",
            rules=_unique(rules),
        )


def _upgrades(node: dict, index: Index, depth: int = 0) -> Iterator[dict]:
    if depth > 4:
        return
    for child in node.get("selectionEntries") or []:
        if child.get("type") == "upgrade":
            yield child
    for group in node.get("selectionEntryGroups") or []:
        yield from _upgrades(group, index, depth + 1)
    for link in node.get("entryLinks") or []:
        target = index.get(link.get("targetId"))
        if target is None:
            continue
        if link.get("type") == "selectionEntryGroup":
            yield from _upgrades(target, index, depth + 1)
        elif target.get("type") == "upgrade":
            yield target


def _child_ids(node: Any, depth: int = 0) -> Iterator[str]:
    if depth > 12:
        return
    if isinstance(node, dict):
        if isinstance(node.get("childId"), str):
            yield node["childId"]
        for key in ("modifiers", "modifierGroups", "conditions", "conditionGroups"):
            for child in node.get(key) or []:
                yield from _child_ids(child, depth + 1)
    elif isinstance(node, list):
        for child in node:
            yield from _child_ids(child, depth + 1)


def _enhancement_detachment(entry: dict, by_id: dict, by_name: dict) -> ParsedDetachment | None:
    for child in _child_ids(entry):
        if child in by_id:
            return by_id[child]
    comment = str(entry.get("comment") or "").strip().lower()
    return by_name.get(comment)
