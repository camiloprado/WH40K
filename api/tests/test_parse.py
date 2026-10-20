from __future__ import annotations

import json
import time
from pathlib import Path

from app.services.parse import parse
from app.services.parse.normalize import normalize_input

ROOT = Path(__file__).resolve().parents[2]


def _text(name: str) -> str:
    return (ROOT / "fixtures" / "text" / name).read_text(encoding="utf-8")


def test_abbrev_header_pair_and_hash_stable():
    raw = _text("daemons_abbrev.txt")
    result = parse(raw.replace("\n", "\r\n"))
    again = parse(normalize_input(raw + "\x00"))
    assert result.format == "nr_text_simple"
    assert result.parse_hash == again.parse_hash
    assert result.header.faction_name == "Chaos - Chaos Daemons"
    assert result.header.detachments[0].name == "Daemonic Incursion"
    assert result.header.detachments[0].variant == "Warp Rifts"
    assert result.header.total_points_declared == 1975
    assert result.header.secondaries[0].startswith("Bring It Down")
    assert result.generator.startswith("newrecruit.eu")
    assert len(result.leader_pairs) == 1
    pair = result.leader_pairs[0]
    assert pair.leader_name == "Poxbringer"
    assert pair.bodyguard_name == "Plaguebearers"
    guo = next(unit for unit in result.units if unit.name == "Great Unclean One")
    assert any(item.name == "Plague flail" and item.count == 2 for item in guo.wargear)
    bearers = next(unit for unit in result.units if unit.name == "Plaguebearers")
    assert bearers.models[0].wargear[0].count == 7
    assert any(item.name == "Instrument of Chaos" for item in bearers.models[0].wargear)
    assert any(warning.reason == "enhancement_sum" for warning in result.warnings)
    assert any(warning.reason == "warlord_missing" for warning in result.warnings)


def test_full_list_is_1975_with_pair():
    result = parse(_text("daemons_1975.txt"))
    assert result.header.total_points_declared == 1975
    assert result.header.points_sum == 1975
    assert result.header.points_include_enhancement is True
    assert not any(warning.reason == "enhancement_sum" for warning in result.warnings)
    assert any(unit.is_warlord and unit.name == "Shalaxi Helbane" for unit in result.units)
    assert len(result.leader_pairs) == 1
    assert result.leader_pairs[0].bodyguard_name == "Plaguebearers"


def test_parentheses_and_two_same_units():
    raw = """
+++++++++++++++++++++++++++++++++++++++++++++++
+ FACTION KEYWORD: Chaos - Chaos Daemons
+ DETACHMENT: Daemonic Incursion
+ TOTAL ARMY POINTS: 200pts
+++++++++++++++++++++++++++++++++++++++++++++++
Char1: 1x Beast (of Nurgle) (100 pts): Claws
Leading Plaguebearers[2]
10x Plaguebearers (50 pts): Sword
10x Plaguebearers (50 pts): Sword
""".strip()
    result = parse(raw)
    beast = result.units[0]
    assert beast.name == "Beast (of Nurgle)"
    assert beast.points == 100
    assert len(result.leader_pairs) == 1
    assert result.leader_pairs[0].bodyguard_line == result.units[2].line_no


def test_truncated_line_does_not_match():
    blob = "1x " + ("A" * 520) + " (10 pts)"
    raw = "+ FACTION KEYWORD: X\n" + blob
    result = parse(raw)
    assert result.units == []
    assert any(warning.reason == "truncated" for warning in result.warnings)


def test_attached_closes_model_group():
    raw = """
+ FACTION KEYWORD: Chaos - Chaos Daemons
+ TOTAL ARMY POINTS: 175pts
Char4: 1x Poxbringer (60 pts): Foul balesword
10x Plaguebearers (115 pts)
• 9x Plaguebearer
    7 with Plaguesword
  Attached to Poxbringer
    5 with ShouldNotApply
""".strip()
    result = parse(raw)
    bearers = next(unit for unit in result.units if unit.name == "Plaguebearers")
    names = [item.name for item in bearers.models[0].wargear]
    assert names == ["Plaguesword"]
    assert result.leader_pairs[0].leader_name == "Poxbringer"


def test_faction_missing_and_unknown_format():
    result = parse("1x Thing (10 pts): Stick")
    assert result.format == "nr_text_unknown"
    assert any(warning.reason == "faction_missing" for warning in result.warnings)
    assert any(warning.reason == "unknown_format" for warning in result.warnings)


def test_wtc_detection_and_two_enhancements():
    raw = """
##### WTC COMPACT #####
FACTION: Chaos - Chaos Daemons
DETACHMENT: Daemonic Incursion
TOTAL: 90
1x Alpha (40 pts): Sword
Enhancement: Gift (+10 pts)
1x Beta (40 pts): Sword
Enhancement: Other (+10 pts)
""".strip()
    result = parse(raw)
    assert result.format == "nr_text_wtc_compact"
    assert result.header.points_include_enhancement is None
    assert any(warning.reason == "enhancement_sum" for warning in result.warnings)


def test_enhancement_not_included_matches_sum():
    raw = """
+ FACTION KEYWORD: Chaos - Chaos Daemons
+ TOTAL ARMY POINTS: 50pts
1x Alpha (40 pts): Sword
Enhancement: Gift (+10 pts)
""".strip()
    result = parse(raw)
    assert result.header.points_include_enhancement is False


def test_zero_enhancement_is_included():
    raw = """
+ FACTION KEYWORD: Chaos - Chaos Daemons
+ TOTAL ARMY POINTS: 40pts
1x Alpha (40 pts): Sword
Enhancement: Gift (+0 pts)
""".strip()
    result = parse(raw)
    assert result.header.points_include_enhancement is True
    assert not any(warning.reason == "enhancement_sum" for warning in result.warnings)


def test_json_11e_newrecruit_shape():
    payload = json.loads((ROOT / "fixtures" / "json" / "daemons_11e_nr.json").read_text(encoding="utf-8"))
    result = parse(json.dumps(payload))
    dumped = result.model_dump_json()
    assert "SHOULD BE DROPPED" not in dumped
    assert result.generator == "https://newrecruit.eu"
    assert result.header.faction_name == "Chaos - Chaos Daemons"
    assert result.header.detachments[0].name == "Daemonic Incursion"
    assert result.header.force_disposition == "Disruption"
    assert result.header.battle_size == "Strike Force"
    assert result.header.points_limit == 2000
    assert result.header.list_name == "O Banquete Podre"
    assert result.header.total_points_declared == 1180
    names = [unit.name for unit in result.units]
    assert names == [
        "Shalaxi Helbane",
        "Great Unclean One",
        "Poxbringer",
        "Daemonettes",
        "Plaguebearers",
        "Plaguebearers",
        "Nurgle Soul Grinder",
    ]
    assert not any(name in {"Battle Size", "Detachment", "Force Disposition", "Show/Hide Options"} for name in names)
    shalaxi = result.units[0]
    assert shalaxi.is_warlord and shalaxi.is_character
    assert [item.name for item in shalaxi.wargear] == [
        "Pavane of Slaanesh - witchfire",
        "Pavane of Slaanesh - focused witchfire",
    ]
    assert shalaxi.wargear[0].stats is not None
    assert shalaxi.wargear[0].stats.attacks == "D6"
    assert shalaxi.wargear[0].stats.skill == 2
    assert shalaxi.wargear[0].stats.keywords == ["Psychic"]
    assert shalaxi.movement == 14
    assert shalaxi.toughness == 10
    assert shalaxi.save == 3
    assert shalaxi.wounds == 20
    assert shalaxi.leadership == 6
    assert shalaxi.oc == 5
    assert shalaxi.invuln == 4
    assert shalaxi.fnp == 4
    assert shalaxi.base_size_mm == "100mm"
    assert shalaxi.ability_names == ["No Prey Can Evade"]
    guo = result.units[1]
    assert guo.enhancement_name == "The Endless Gift"
    assert guo.enhancement_points == 30
    assert guo.wargear[0].stats is not None
    assert guo.wargear[0].stats.attacks == "D6+3"
    daemons = next(unit for unit in result.units if unit.name == "Daemonettes")
    assert daemons.model_count == 10
    assert [model.name for model in daemons.models] == ["Alluress", "Daemonette"]
    assert daemons.models[1].count == 9
    assert any(item.name == "Daemonic Icon" and item.stats is None for item in daemons.wargear)
    assert result.header.points_include_enhancement is False
    assert len(result.leader_pairs) == 1
    assert result.leader_pairs[0].leader_name == "Poxbringer"
    assert result.leader_pairs[0].bodyguard_path == result.units[4].json_path


def test_json_reads_other_battle_sizes():
    payload = {
        "roster": {
            "name": "Army Roster",
            "gameSystemName": "Warhammer 40,000 11th Edition",
            "costs": [{"name": "pts", "value": 990}],
            "forces": [
                {
                    "catalogueName": "Chaos - Chaos Daemons",
                    "selections": [
                        {
                            "name": "Battle Size",
                            "type": "upgrade",
                            "selections": [{"name": "Incursion (1000 Point limit)", "type": "upgrade"}],
                        },
                        {"name": "Bloodletters", "type": "unit", "number": 10, "costs": [{"name": "pts", "value": 110}]},
                    ],
                }
            ],
        }
    }
    result = parse(json.dumps(payload))
    assert result.header.battle_size == "Incursion"
    assert result.header.points_limit == 1000
    assert result.header.list_name is None
    assert [unit.name for unit in result.units] == ["Bloodletters"]


def test_json_discards_rules_and_pairs():
    payload = json.loads((ROOT / "fixtures" / "json" / "daemons_min.json").read_text(encoding="utf-8"))
    result = parse(json.dumps(payload))
    dumped = result.model_dump_json()
    assert "SHOULD BE DROPPED" not in dumped
    assert result.header.total_points_declared == 1975
    assert result.header.faction_name == "Chaos - Chaos Daemons"
    assert result.header.detachments[0].variant == "Warp Rifts"
    assert any(unit.is_warlord and unit.name == "Shalaxi Helbane" for unit in result.units)
    pair = result.leader_pairs[0]
    assert pair.leader_name == "Poxbringer"
    assert pair.bodyguard_name == "Plaguebearers"
    assault = next(unit for unit in result.units if unit.name == "Unidade Assault Fixture")
    assert assault.wargear[0].stats is not None
    assert "ASSAULT" in assault.wargear[0].stats.keywords
    assert assault.wargear[0].stats.attacks == "D6"
    daemons = next(unit for unit in result.units if unit.name == "Daemonettes")
    assert daemons.wargear[0].stats.keywords == []


def test_json_depth_and_speed():
    node: dict = {"name": "leaf", "type": "unit", "costs": [{"name": "pts", "value": 1}]}
    for _ in range(25):
        node = {"selections": [node]}
    started = time.perf_counter()
    result = parse(json.dumps({"roster": {"forces": [{"catalogueName": "X", "selections": [node]}]}}))
    assert time.perf_counter() - started < 0.3
    assert any(warning.reason == "max_depth" for warning in result.warnings)

    started = time.perf_counter()
    parse("(((((" * 4000)
    assert time.perf_counter() - started < 0.3

    started = time.perf_counter()
    parse(" " * 10000)
    assert time.perf_counter() - started < 0.3

    lines = "\n".join(["1x Zerg (1 pts): Claw"] * 6000)
    started = time.perf_counter()
    capped = parse("+ FACTION KEYWORD: X\n" + lines)
    assert time.perf_counter() - started < 0.3
    assert any(warning.reason == "too_many_lines" for warning in capped.warnings)
    assert len(capped.units) <= 5000


def test_multi_detachment_lines():
    raw = """
+ FACTION KEYWORD: Chaos - Chaos Daemons
+ DETACHMENT: Daemonic Incursion (Warp Rifts)
+ DETACHMENT: Shadow Legion
+ TOTAL ARMY POINTS: 10pts
1x Scout (10 pts): Knife
""".strip()
    result = parse(raw)
    assert [item.name for item in result.header.detachments] == ["Daemonic Incursion", "Shadow Legion"]


def test_known_detachment_comma_split():
    raw = """
##### WTC FULL #####
FACTION: Adeptus Mechanicus
DETACHMENT: Rad-Zone Corps, Skitarii Hunter Cohort
TOTAL: 10
1x Ranger (10 pts): Gun
""".strip()
    result = parse(raw, known_detachments=["Rad-Zone Corps", "Skitarii Hunter Cohort"])
    assert result.format == "nr_text_wtc_full"
    assert [item.name for item in result.header.detachments] == ["Rad-Zone Corps", "Skitarii Hunter Cohort"]
