import json
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db import session_factory
from app.models import Ability, Detachment, Faction, RuleEffect
from app.services.cheatsheet import commit_rows
from app.services.views import upsert_effect

CORE = [
    ("command", "No começo do turno, confira CP e os lembretes da facção. HIPÓTESE até você revisar."),
    (
        "battle_shock",
        "Teste quem está em battle-shock ou na metade da força ou abaixo. Só sai do battle-shock quem já estava nele e passou. Falhou: fica em battle-shock.",
    ),
    ("movement", "Quem já moveu ou está destruído não entra de novo no movimento."),
    (
        "shooting",
        "Quem avançou só atira com ASSAULT. Atirar num MONSTER/VEHICLE inimigo engajado: −1 para acertar, exceto CLOSE-QUARTERS de quem está engajado com ele (Core 17.03).",
    ),
    (
        "charge",
        "Quem avançou, recuou ou está engajado não carrega, salvo permissão. Lembrete: precisa de inimigo a 12\".",
    ),
    (
        "fight",
        "Lutam as engajadas, as que carregaram, ou as que estavam engajadas no começo do Fight. Desengajada elegível → Overrun (pile-in extra).",
    ),
    ("end_of_turn", "Feche missões, secundárias e ações antes de passar o turno."),
]


def main() -> None:
    db = session_factory()()
    try:
        for phase, text in CORE:
            ability = db.scalar(select(Ability).where(Ability.kind == "core", Ability.name == phase))
            if ability is None:
                ability = Ability(kind="core", name=phase, summary_user=text, is_hypothesis=True)
                db.add(ability)
                db.flush()
            elif phase in ("battle_shock", "charge", "fight", "shooting"):
                ability.summary_user = text
            exists = db.scalar(
                select(RuleEffect).where(RuleEffect.ability_id == ability.id, RuleEffect.phase == phase)
            )
            if exists is None:
                upsert_effect(
                    db,
                    ability.id,
                    {
                        "phase": phase,
                        "timing": "during",
                        "effect_kind": "reminder",
                        "owner_label": "Geral",
                        "effect_text": text,
                        "is_hypothesis": True,
                    },
                )
            elif phase in ("battle_shock", "charge", "fight", "shooting"):
                exists.effect_text = text
                exists.is_hypothesis = True
        faction = db.scalar(select(Faction).where(Faction.name == "Chaos - Chaos Daemons"))
        if faction is None:
            faction = Faction(name="Chaos - Chaos Daemons", source="user", accent_color="#6E2430")
            db.add(faction)
            db.flush()
        detachment = db.scalar(
            select(Detachment).where(Detachment.faction_id == faction.id, Detachment.name == "Daemonic Incursion")
        )
        if detachment is None:
            detachment = Detachment(faction_id=faction.id, name="Daemonic Incursion", variant="Warp Rifts")
            db.add(detachment)
            db.flush()
        plague = db.scalar(
            select(Detachment).where(Detachment.faction_id == faction.id, Detachment.name == "Plague Legion")
        )
        if plague is None:
            plague = Detachment(faction_id=faction.id, name="Plague Legion")
            db.add(plague)
            db.flush()
        example = db.scalar(
            select(Ability).where(Ability.kind == "stratagem", Ability.name == "Exemplo — gastar 1 CP")
        )
        if example is None:
            example = Ability(
                kind="stratagem",
                detachment_id=detachment.id,
                name="Exemplo — gastar 1 CP",
                cp_cost=1,
                use_limit="per_phase",
                usable_turn="either",
                summary_user="Exemplo pessoal para treinar o gasto de CP. Não é uma stratagem de livro.",
                is_hypothesis=True,
            )
            db.add(example)
            db.flush()
            upsert_effect(
                db,
                example.id,
                {
                    "phase": "any",
                    "effect_kind": "stratagem",
                    "owner_label": "Daemonic Incursion",
                    "effect_text": "Exemplo pessoal: gasta 1 CP uma vez por fase.",
                    "is_hypothesis": True,
                },
            )
        _seed_shadow_effects(db, faction.id, plague.id)
        file = Path("seeds/belakor.json")
        if not file.exists():
            file = Path("../fixtures/seed/belakor.sample.json")
        if file.exists() and os_env_version():
            payload = json.loads(file.read_text(encoding="utf-8"))
            if payload.get("version_id"):
                commit_rows(db, int(payload["version_id"]), payload.get("rows") or [])
            else:
                for row in payload.get("rows") or []:
                    row.setdefault("owner", {"kind": "general", "name": row.get("owner_label") or "Be'lakor"})
                    commit_via_general(db, row)
        db.commit()
    finally:
        db.close()


def _seed_shadow_effects(db, faction_id: int, plague_detachment_id: int) -> None:
    """Paráfrases do Faction Pack Daemons — sem texto de regra copiado (Daemons p. 2, 131)."""
    rows = [
        {
            "name": "Daemonic Manifestation",
            "phase": "battle_shock",
            "effect_kind": "prompt",
            "is_hypothesis": False,
            "turn_owner": "own",
            "detachment_id": None,
            "text": "Unidade sua no Shadow: +1 no teste. Passou: cura D3 num modelo; Battleline: volta até D3 modelos (sem CHARACTER). Insane Bravery conta como passou.",
            "condition_json": {"game.shadow_of_chaos": "own_dz"},
        },
        {
            "name": "Daemonic Manifestation (outros testes)",
            "phase": "any",
            "effect_kind": "reminder",
            "is_hypothesis": False,
            "turn_owner": "own",
            "detachment_id": None,
            "text": "Manifestation também vale em testes fora da Command (ex.: Desperate Escape), se a unidade estiver no Shadow.",
            "condition_json": {"game.shadow_of_chaos": "own_dz"},
        },
        {
            "name": "Daemonic Terror",
            "phase": "battle_shock",
            "effect_kind": "reminder",
            "is_hypothesis": True,
            "turn_owner": "opponent",
            "detachment_id": None,
            "text": "Inimigo no seu Shadow ou a 6\" de Greater Daemon: −1 no teste; falhou: D3 mortal wounds. Distância: lembrete manual.",
            "condition_json": {},
        },
        {
            "name": "Plague Legion — Shadow",
            "phase": "command",
            "effect_kind": "reminder",
            "is_hypothesis": True,
            "turn_owner": "both",
            "detachment_id": plague_detachment_id,
            "text": "Escolha um inimigo no seu Shadow (inclui a 9\" de Nurgle): ele faz teste de battle-shock. Só com destacamento Plague Legion.",
            "condition_json": {"game.shadow_of_chaos": "own_dz"},
        },
    ]
    for row in rows:
        ability = db.scalar(
            select(Ability).where(Ability.kind == "faction", Ability.faction_id == faction_id, Ability.name == row["name"])
        )
        if ability is None:
            ability = Ability(
                kind="faction",
                faction_id=faction_id,
                detachment_id=row["detachment_id"],
                name=row["name"],
                summary_user=row["text"],
                is_hypothesis=row["is_hypothesis"],
                source="user",
            )
            db.add(ability)
            db.flush()
        else:
            ability.summary_user = row["text"]
            ability.is_hypothesis = row["is_hypothesis"]
            ability.detachment_id = row["detachment_id"]
        exists = db.scalar(
            select(RuleEffect).where(RuleEffect.ability_id == ability.id, RuleEffect.phase == row["phase"])
        )
        payload = {
            "phase": row["phase"],
            "timing": "during",
            "effect_kind": row["effect_kind"],
            "owner_label": "Chaos Daemons",
            "effect_text": row["text"],
            "is_hypothesis": row["is_hypothesis"],
            "condition_json": row["condition_json"],
            "turn_owner": row["turn_owner"],
        }
        if exists is None:
            upsert_effect(db, ability.id, payload)
        else:
            exists.effect_text = row["text"]
            exists.is_hypothesis = row["is_hypothesis"]
            exists.turn_owner = row["turn_owner"]
            exists.condition_json = row["condition_json"]
            exists.effect_kind = row["effect_kind"]


def os_env_version() -> bool:
    return True


def commit_via_general(db, row: dict) -> None:
    from app.services.cheatsheet import _ability

    ability = _ability(db, 0, row)
    exists = db.scalar(
        select(RuleEffect).where(
            RuleEffect.ability_id == ability.id,
            RuleEffect.phase == (row.get("phase") or "any"),
        )
    )
    if exists is None:
        upsert_effect(
            db,
            ability.id,
            {
                "phase": row.get("phase") or "any",
                "timing": row.get("timing") or "during",
                "effect_kind": row.get("effect_kind") or "reminder",
                "owner_label": row.get("owner_label") or "Geral",
                "effect_text": row.get("effect_text") or row.get("text") or "",
                "is_hypothesis": True,
            },
        )


if __name__ == "__main__":
    main()
