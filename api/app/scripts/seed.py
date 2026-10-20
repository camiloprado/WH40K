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
    ("shooting", "Quem avançou só atira com armas ASSAULT, salvo uma permissão que você cadastrou."),
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
            elif phase in ("battle_shock", "charge", "fight"):
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
            elif phase in ("battle_shock", "charge", "fight"):
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
        _seed_shadow_effects(db, faction.id, detachment.id)
        seed_path = Path(get_settings().model_config.get("env_file") or ".") 
        file = Path("seeds/belakor.json")
        if not file.exists():
            file = Path("../fixtures/seed/belakor.sample.json")
        if file.exists() and os_env_version():
            payload = json.loads(file.read_text(encoding="utf-8"))
            # Colinha geral não precisa de versão; grava direto se houver version_id no arquivo.
            if payload.get("version_id"):
                commit_rows(db, int(payload["version_id"]), payload.get("rows") or [])
            else:
                for row in payload.get("rows") or []:
                    row.setdefault("owner", {"kind": "general", "name": row.get("owner_label") or "Be'lakor"})
                    from app.models import ArmyList

                    commit_via_general(db, row)
        db.commit()
    finally:
        db.close()


def _seed_shadow_effects(db, faction_id: int, detachment_id: int) -> None:
    """Paráfrases do Faction Pack Daemons — sem texto de regra copiado."""
    rows = [
        (
            "Daemonic Manifestation",
            "battle_shock",
            "prompt",
            False,
            "Unidade sua no Shadow: +1 no teste. Passou: cura D3 num modelo; Battleline: volta até D3 modelos (sem CHARACTER). Insane Bravery conta como passou.",
            {"game.shadow_of_chaos": "own_dz"},
        ),
        (
            "Daemonic Manifestation (outros testes)",
            "any",
            "reminder",
            False,
            "Manifestation também vale em testes fora da Command (ex.: Desperate Escape), se a unidade estiver no Shadow.",
            {"game.shadow_of_chaos": "own_dz"},
        ),
        (
            "Daemonic Terror",
            "battle_shock",
            "reminder",
            True,
            "Inimigo no seu Shadow ou a 6\" de Greater Daemon: −1 no teste; falhou: D3 mortal wounds. Distância: lembrete manual.",
            {"game.shadow_of_chaos": "nml"},
        ),
        (
            "Plague Legion — Shadow",
            "command",
            "reminder",
            True,
            "Escolha um inimigo no seu Shadow (inclui a 9\" de Nurgle): ele faz teste de battle-shock. Só com destacamento Plague Legion.",
            {"game.shadow_of_chaos": "own_dz"},
        ),
    ]
    for name, phase, kind, hypothesis, text, condition in rows:
        ability = db.scalar(
            select(Ability).where(Ability.kind == "faction", Ability.faction_id == faction_id, Ability.name == name)
        )
        if ability is None:
            ability = Ability(
                kind="faction",
                faction_id=faction_id,
                name=name,
                summary_user=text,
                is_hypothesis=hypothesis,
                source="user",
            )
            db.add(ability)
            db.flush()
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
                    "effect_kind": kind,
                    "owner_label": "Chaos Daemons",
                    "effect_text": text,
                    "is_hypothesis": hypothesis,
                    "condition_json": condition,
                },
            )


def os_env_version() -> bool:
    return True


def commit_via_general(db, row: dict) -> None:
    from app.services.cheatsheet import _ability

    ability = _ability(db, 0, row)
    exists = db.scalar(
        select(RuleEffect).where(
            RuleEffect.ability_id == ability.id,
            RuleEffect.phase == row["phase"],
            RuleEffect.effect_text == row["text"],
        )
    )
    if exists:
        return
    upsert_effect(
        db,
        ability.id,
        {
            "phase": row["phase"],
            "timing": row.get("timing") or "during",
            "effect_kind": "reminder",
            "owner_label": row.get("owner_label") or "Be'lakor",
            "effect_text": row["text"],
            "is_hypothesis": True,
        },
    )


if __name__ == "__main__":
    main()
