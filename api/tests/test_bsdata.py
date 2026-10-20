import uuid

import pytest

from app.services.bsdata import fetch
from app.services.bsdata.parse import choice_count, choice_scope, guess_effect, parse_faction
from app.services.bsdata.sync import PLACEHOLDER
from tests.test_api import _client

SHA = "a" * 40
SECRET = "Texto inventado que nunca deve ir para o banco"


def _fixture(tag: str) -> tuple[str, dict]:
    main = f"Test - Ember Host {tag}.json"
    library = f"Test - Ember Host {tag} Library.json"
    lord = {
        "id": "u-lord",
        "name": "Cinder Lord",
        "type": "model",
        "categoryLinks": [{"name": "Character", "targetId": "c1"}, {"name": "Faction: Ember Host", "targetId": "c2"}],
        "profiles": [
            {
                "id": "p-unit",
                "name": "Cinder Lord",
                "typeName": "Unit",
                "characteristics": [
                    {"name": "M", "$text": "6\""},
                    {"name": "T", "$text": "5"},
                    {"name": "SV", "$text": "3+"},
                    {"name": "W", "$text": "6"},
                    {"name": "LD", "$text": "6+"},
                    {"name": "OC", "$text": "1"},
                ],
            },
            {
                "id": "p-oaths",
                "name": "Twin Oaths",
                "typeName": "Abilities",
                "characteristics": [
                    {"name": "Description", "$text": f"At the start of your Command phase, select two of the following. {SECRET}"}
                ],
            },
            {"id": "p-a", "name": "Oath of Coals", "typeName": "Twin Oaths", "characteristics": [{"name": "Effect", "$text": SECRET}]},
            {"id": "p-b", "name": "Oath of Smoke", "typeName": "Twin Oaths", "characteristics": [{"name": "Effect", "$text": SECRET}]},
            {"id": "p-c", "name": "Oath of Sparks", "typeName": "Twin Oaths", "characteristics": [{"name": "Effect", "$text": SECRET}]},
            {"id": "p-inv", "name": "Invulnerable Save", "typeName": "Abilities", "characteristics": [{"name": "Description", "$text": "4+"}]},
            {"id": "p-lead", "name": "Leader", "typeName": "Abilities", "characteristics": [{"name": "Description", "$text": SECRET}]},
            {
                "id": "p-calm",
                "name": "Steady Glow",
                "typeName": "Abilities",
                "characteristics": [{"name": "Description", "$text": f"While this model is near friends. {SECRET}"}],
            },
        ],
        "infoLinks": [{"name": "Ember Tide", "type": "rule", "targetId": "r-tide"}],
        "selectionEntries": [
            {
                "id": "w-blade",
                "name": "Ember blade",
                "type": "upgrade",
                "profiles": [
                    {
                        "id": "p-blade",
                        "name": "➤ Ember blade",
                        "typeName": "Melee Weapons",
                        "characteristics": [
                            {"name": "Range", "$text": "Melee"},
                            {"name": "A", "$text": "5"},
                            {"name": "WS", "$text": "2+"},
                            {"name": "S", "$text": "6"},
                            {"name": "AP", "$text": "-2"},
                            {"name": "D", "$text": "D3+1"},
                            {"name": "Keywords", "$text": "Lethal Hits, Precision"},
                        ],
                    }
                ],
            }
        ],
        "entryLinks": [{"name": "Enhancements", "targetId": "g-enh", "type": "selectionEntryGroup"}],
    }
    detachment = {
        "id": "e-det",
        "name": "Detachment",
        "type": "upgrade",
        "selectionEntryGroups": [
            {
                "id": "g-det",
                "name": "Detachment",
                "selectionEntries": [
                    {
                        "id": "d-ash",
                        "name": "Ashen Pact",
                        "type": "upgrade",
                        "rules": [{"id": "r-pact", "name": "Pact of Ash", "description": f"At the start of the battle, select one. {SECRET}"}],
                    }
                ],
            }
        ],
    }
    enhancements = {
        "id": "g-enh",
        "name": "Enhancements",
        "selectionEntries": [
            {
                "id": "x-brand",
                "name": "Glowing Brand",
                "type": "upgrade",
                "costs": [{"name": "pts", "value": 20.0}],
                "modifiers": [{"type": "set", "conditions": [{"type": "notInstanceOf", "childId": "d-ash"}]}],
                "profiles": [
                    {
                        "id": "p-brand",
                        "name": "Glowing Brand",
                        "typeName": "Abilities",
                        "characteristics": [{"name": "Description", "$text": f"In the Fight phase, the bearer glows. {SECRET}"}],
                    }
                ],
            }
        ],
    }
    catalogues = {
        main: {
            "id": f"cat-{tag}",
            "name": main[:-5],
            "revision": 3,
            "catalogueLinks": [{"name": library[:-5], "targetId": f"lib-{tag}", "importRootEntries": True}],
            "entryLinks": [{"name": "Cinder Lord", "targetId": "u-lord", "type": "selectionEntry"}],
        },
        library: {
            "id": f"lib-{tag}",
            "name": library[:-5],
            "library": True,
            "selectionEntries": [detachment],
            "sharedSelectionEntries": [lord],
            "sharedSelectionEntryGroups": [enhancements],
            "sharedRules": [{"id": "r-tide", "name": "Ember Tide", "description": f"In your opponent's Shooting phase. {SECRET}"}],
        },
    }
    return main, catalogues


def test_guess_effect_heuristics():
    assert guess_effect("At the start of your Command phase, do it").__dict__ == {"phase": "command", "turn_owner": "own", "timing": "start"}
    assert guess_effect("In your opponent's Shooting phase, after").__dict__ == {"phase": "shooting", "turn_owner": "opponent", "timing": "during"}
    assert guess_effect("At the end of the Fight phase, roll").__dict__ == {"phase": "fight", "turn_owner": "own", "timing": "end"}
    assert guess_effect("At the end of your turn, if").phase == "end_of_turn"
    assert guess_effect("When this unit is set up during Declare Battle Formations").phase == "deployment"
    assert guess_effect("While this model is leading a unit") is None
    assert choice_count("select two of the following") == 2
    assert choice_count("choose 3 abilities") == 3
    assert choice_count("each time") is None
    assert choice_scope("At the start of the battle, select one") == "battle"
    assert choice_scope("At the start of each battle round") == "round"


def test_parse_skeleton_keeps_structure_and_drops_text():
    main, catalogues = _fixture("p")
    parsed = parse_faction(catalogues, main, "wh40k-11e@x")
    assert [unit.name for unit in parsed.units] == ["Cinder Lord"]
    lord = parsed.units[0]
    assert lord.stats == {"movement": 6, "toughness": 5, "save": 3, "wounds": 6, "leadership": 6, "oc": 1, "invuln": 4}
    assert lord.is_character
    assert lord.weapons[0]["name"] == "Ember blade"
    assert lord.weapons[0]["damage"] == "D3+1"
    assert lord.weapons[0]["keywords"] == ["LETHAL HITS", "PRECISION"]
    names = [item.name for item in lord.abilities]
    assert "Leader" not in names and "Invulnerable Save" not in names
    oaths = next(item for item in lord.abilities if item.name == "Twin Oaths")
    assert oaths.options == ["Oath of Coals", "Oath of Smoke", "Oath of Sparks"]
    assert oaths.count == 2
    assert oaths.guess.phase == "command" and oaths.guess.timing == "start"
    assert next(item for item in lord.abilities if item.name == "Steady Glow").guess is None
    assert [rule.name for rule in parsed.faction_rules] == ["Ember Tide"]
    assert parsed.faction_rules[0].guess.turn_owner == "opponent"
    pact = parsed.detachments[0]
    assert pact.name == "Ashen Pact"
    assert pact.rules[0].scope == "battle"
    assert [(item.name, item.points) for item in pact.enhancements] == [("Glowing Brand", 20)]
    assert SECRET not in repr(parsed)


@pytest.fixture
def fake_github(monkeypatch):
    tag = uuid.uuid4().hex[:6]
    main, catalogues = _fixture(tag)
    files = [{"name": name, "size": 100, "library": "Library" in name, "system": False} for name in catalogues]
    monkeypatch.setattr(fetch, "tree", lambda repo, sha: files)
    monkeypatch.setattr(fetch.Loader, "load", lambda self, name: catalogues[name])
    return main


def test_import_diff_then_apply_is_idempotent(fake_github):
    client = _client()
    body = {"repo": "wh40k-11e", "sha": SHA, "catalogue": fake_github}
    dry = client.post("/api/v1/bsdata/import", json=body)
    assert dry.status_code == 200, dry.text
    counts = dry.json()["counts"]
    assert counts["datasheets"]["added"] == 1
    assert counts["detachments"]["added"] == 1
    assert counts["enhancements"]["added"] == 1
    assert counts["effects"]["added"] == 4
    assert dry.json()["faction"]["id"] is None
    assert all(item["catalogue"] != fake_github for item in client.get("/api/v1/bsdata/imports").json())

    applied = client.post("/api/v1/bsdata/import", json={**body, "apply": True})
    assert applied.status_code == 200, applied.text
    faction_id = applied.json()["faction"]["id"]
    sheets = [row for row in client.get("/api/v1/datasheets").json() if row["faction_id"] == faction_id]
    assert sheets[0]["invuln"] == 4 and sheets[0]["source"] == "bsdata" and not sheets[0]["is_stub"]
    abilities = [row for row in client.get("/api/v1/abilities").json() if row["source"] == "bsdata" and row["datasheet_id"] == sheets[0]["id"]]
    oaths = next(row for row in abilities if row["name"] == "Twin Oaths")
    assert oaths["summary_user"] is None and oaths["is_hypothesis"]
    effects = client.get(f"/api/v1/abilities/{oaths['id']}/effects").json()
    assert effects[0]["choice_options"] == ["Oath of Coals", "Oath of Smoke", "Oath of Sparks"]
    assert effects[0]["choice_count"] == 2
    assert effects[0]["effect_kind"] == "prompt"
    assert effects[0]["effect_text"] == PLACEHOLDER
    everything = repr(client.get("/api/v1/effects").json()) + repr(client.get("/api/v1/abilities").json())
    assert SECRET not in everything
    enhancement = next(row for row in client.get("/api/v1/enhancements").json() if row["name"] == "Glowing Brand" and row["source"] == "bsdata")
    assert enhancement["points"] == 20 and enhancement["ability_id"]

    again = client.post("/api/v1/bsdata/import", json={**body, "apply": True}).json()["counts"]
    assert all(group["added"] == 0 and group["changed"] == 0 for group in again.values())
    assert again["datasheets"]["same"] == 1
    history = [item for item in client.get("/api/v1/bsdata/imports").json() if item["catalogue"] == fake_github]
    assert len(history) == 2 and history[0]["sha"] == SHA


def test_import_keeps_user_edits(fake_github):
    client = _client()
    body = {"repo": "wh40k-11e", "sha": SHA, "catalogue": fake_github, "apply": True}
    faction_id = client.post("/api/v1/bsdata/import", json=body).json()["faction"]["id"]
    sheet = next(row for row in client.get("/api/v1/datasheets").json() if row["faction_id"] == faction_id)
    assert client.patch(f"/api/v1/datasheets/{sheet['id']}", json={"toughness": 9, "source": "user"}).status_code == 200
    oaths = next(row for row in client.get("/api/v1/abilities").json() if row["datasheet_id"] == sheet["id"] and row["name"] == "Twin Oaths")
    client.patch(f"/api/v1/abilities/{oaths['id']}", json={"summary_user": "Meu resumo"})
    result = client.post("/api/v1/bsdata/import", json=body).json()
    assert result["changes"]["datasheets"]["kept"] == [{"name": "Cinder Lord", "fields": ["toughness"]}]
    assert next(row for row in client.get("/api/v1/datasheets").json() if row["id"] == sheet["id"])["toughness"] == 9
    assert next(row for row in client.get("/api/v1/abilities").json() if row["id"] == oaths["id"])["summary_user"] == "Meu resumo"
    assert len(client.get(f"/api/v1/abilities/{oaths['id']}/effects").json()) == 1


def test_import_rejects_bad_input(fake_github):
    client = _client()
    assert client.post("/api/v1/bsdata/import", json={"repo": "evil/repo", "sha": SHA, "catalogue": fake_github}).status_code == 422
    assert client.post("/api/v1/bsdata/import", json={"repo": "wh40k-11e", "sha": "main", "catalogue": fake_github}).status_code == 422
    missing = client.post("/api/v1/bsdata/import", json={"repo": "wh40k-11e", "sha": SHA, "catalogue": "Nope - Nope.json"})
    assert missing.status_code == 422
    library = fake_github[:-5] + " Library.json"
    assert client.post("/api/v1/bsdata/import", json={"repo": "wh40k-11e", "sha": SHA, "catalogue": library}).status_code == 422
