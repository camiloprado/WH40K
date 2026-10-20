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
                ability = Ability(kind="core", name=phase, summary_user=text, is_hypothesis=False)
                db.add(ability)
                db.flush()
            else:
                ability.summary_user = text
                ability.is_hypothesis = False
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
                        "is_hypothesis": False,
                    },
                )
            else:
                exists.effect_text = text
                exists.is_hypothesis = False
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
        core_det = _ensure_core_detachment(db)
        _seed_core_stratagems(db, core_det.id)
        _seed_daemonic_invulnerability(db, detachment.id)
        _seed_tyranid_profiles(db)
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
        # CHECK: faction → só faction_id; detachment → só detachment_id.
        if row["detachment_id"] is not None:
            kind = "detachment"
            ability = db.scalar(
                select(Ability).where(
                    Ability.kind.in_(("detachment", "faction")),
                    Ability.name == row["name"],
                )
            )
        else:
            kind = "faction"
            ability = db.scalar(
                select(Ability).where(
                    Ability.kind == "faction",
                    Ability.faction_id == faction_id,
                    Ability.name == row["name"],
                )
            )
        if ability is None:
            ability = Ability(
                kind=kind,
                faction_id=None if kind == "detachment" else faction_id,
                detachment_id=row["detachment_id"],
                name=row["name"],
                summary_user=row["text"],
                is_hypothesis=row["is_hypothesis"],
                source="user",
            )
            db.add(ability)
            db.flush()
        else:
            ability.kind = kind
            ability.faction_id = None if kind == "detachment" else faction_id
            ability.detachment_id = row["detachment_id"]
            ability.summary_user = row["text"]
            ability.is_hypothesis = row["is_hypothesis"]
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


def _ensure_core_detachment(db) -> Detachment:
    """Stratagems Core exigem detachment_id no CHECK de abilities."""
    faction = db.scalar(select(Faction).where(Faction.name == "Core Rules"))
    if faction is None:
        faction = Faction(name="Core Rules", source="user", accent_color="#888888")
        db.add(faction)
        db.flush()
    det = db.scalar(
        select(Detachment).where(Detachment.faction_id == faction.id, Detachment.name == "Core Stratagems")
    )
    if det is None:
        det = Detachment(faction_id=faction.id, name="Core Stratagems")
        db.add(det)
        db.flush()
    return det


def _seed_core_stratagems(db, detachment_id: int) -> None:
    """Paráfrases Core 15.02–15.12 — uma linha cada, sem texto de livro."""
    rows = [
        ("Command Re-roll", "any", "both", "per_phase", 1, "during", "Depois de uma rolagem sua (exceto carga dado a dado), gaste 1 CP para rerrolar."),
        ("Epic Challenge", "fight", "both", "per_phase", 1, "during", "CHARACTER sua escolhida para lutar: um modelo ganha PRECISION no corpo a corpo até o fim da fase."),
        ("Insane Bravery", "battle_shock", "own", "per_battle", 1, "start", "Antes da rolagem na sua Command: o teste de battle-shock passa automaticamente."),
        ("Explosives", "shooting", "own", "per_phase", 1, "during", "Unidade EXPLOSIVES/GRENADES desengajada e apta a atirar (sem avançar) usa a arma de explosivos."),
        ("Crushing Impact", "charge", "own", "per_phase", 1, "end", "Depois que MONSTER/VEHICLE termina o charge move: lembrete de impacto."),
        ("Rapid Ingress", "movement", "opponent", "per_phase", 1, "end", "Fim da Movement do oponente: unidade em reserva (não AIRCRAFT) faz ingress; não na 1ª rodada."),
        ("Fire Overwatch", "movement", "opponent", "per_phase", 1, "end", "Fim da Movement do oponente: unidade desengajada (não TITANIC) faz snap shooting; depois não começa ação nesta fase."),
        ("Smokescreen", "shooting", "opponent", "per_phase", 1, "start", "Começo do Shooting do oponente: unidade SMOKE ganha cobertura até o fim da fase."),
        ("Heroic Intervention", "charge", "opponent", "per_phase", 1, "end", "Fim da Charge do oponente: desengajada a ≤12\" declara carga (Into the Fray +1 CP)."),
        ("Counteroffensive", "fight", "opponent", "per_phase", 2, "during", "Na Fight do oponente, após inimigo resolver ataques: unidade sua apta ganha Fights First e luta em seguida (2 CP)."),
    ]
    for name, phase, turn, limit, cost, timing, text in rows:
        ability = db.scalar(select(Ability).where(Ability.kind == "stratagem", Ability.name == name))
        if ability is None:
            ability = Ability(
                kind="stratagem",
                detachment_id=detachment_id,
                name=name,
                cp_cost=cost,
                use_limit=limit,
                usable_turn="either" if turn == "both" else turn,
                summary_user=text,
                is_hypothesis=False,
                source="user",
            )
            db.add(ability)
            db.flush()
        else:
            ability.detachment_id = detachment_id
            ability.cp_cost = cost
            ability.use_limit = limit
            ability.usable_turn = "either" if turn == "both" else turn
            ability.summary_user = text
            ability.is_hypothesis = False
        exists = db.scalar(
            select(RuleEffect).where(RuleEffect.ability_id == ability.id, RuleEffect.phase == phase)
        )
        payload = {
            "phase": phase,
            "timing": timing,
            "turn_owner": turn,
            "effect_kind": "stratagem",
            "owner_label": "Core",
            "effect_text": text,
            "is_hypothesis": False,
        }
        if exists is None:
            upsert_effect(db, ability.id, payload)
        else:
            exists.effect_text = text
            exists.turn_owner = turn
            exists.timing = timing
            exists.is_hypothesis = False


def _seed_daemonic_invulnerability(db, detachment_id: int) -> None:
    name = "Daemonic Invulnerability"
    text = "Alvo seu rerrola salvamentos invulneráveis de 1 até o fim da fase (Daemons p7)."
    ability = db.scalar(select(Ability).where(Ability.kind == "stratagem", Ability.name == name))
    if ability is None:
        ability = Ability(
            kind="stratagem",
            detachment_id=detachment_id,
            name=name,
            cp_cost=1,
            use_limit="per_phase",
            usable_turn="opponent",
            summary_user=text,
            is_hypothesis=False,
            source="user",
        )
        db.add(ability)
        db.flush()
    else:
        ability.summary_user = text
        ability.detachment_id = detachment_id
        ability.cp_cost = 1
        ability.use_limit = "per_phase"
        ability.usable_turn = "opponent"
        ability.is_hypothesis = False
    exists = db.scalar(
        select(RuleEffect).where(RuleEffect.ability_id == ability.id, RuleEffect.phase == "shooting")
    )
    payload = {
        "phase": "shooting",
        "timing": "during",
        "turn_owner": "opponent",
        "effect_kind": "stratagem",
        "owner_label": "Daemonic Incursion",
        "effect_text": text,
        "is_hypothesis": False,
    }
    if exists is None:
        upsert_effect(db, ability.id, payload)
    else:
        exists.effect_text = text
        exists.turn_owner = "opponent"
        exists.is_hypothesis = False
    _seed_realm_of_chaos(db, detachment_id)


def _seed_realm_of_chaos(db, detachment_id: int) -> None:
    """Daemonic Incursion — Realm of Chaos (Daemons p7). Pré-req de must_ingress (C14)."""
    name = "The Realm of Chaos"
    text = "No fim do turno do oponente: 1 CP; uma unidade sua (não engajada) volta à reserva Strategic; no próximo Movement ela deve fazer ingress (Daemons p7)."
    ability = db.scalar(select(Ability).where(Ability.kind == "stratagem", Ability.name == name))
    if ability is None:
        ability = Ability(
            kind="stratagem",
            detachment_id=detachment_id,
            name=name,
            cp_cost=1,
            use_limit="per_phase",
            usable_turn="opponent",
            summary_user=text,
            is_hypothesis=False,
            source="user",
        )
        db.add(ability)
        db.flush()
    else:
        ability.summary_user = text
        ability.detachment_id = detachment_id
        ability.cp_cost = 1
        ability.use_limit = "per_phase"
        ability.usable_turn = "opponent"
        ability.is_hypothesis = False
    exists = db.scalar(
        select(RuleEffect).where(RuleEffect.ability_id == ability.id, RuleEffect.phase == "end_of_turn")
    )
    payload = {
        "phase": "end_of_turn",
        "timing": "end",
        "turn_owner": "opponent",
        "effect_kind": "stratagem",
        "owner_label": "Daemonic Incursion",
        "effect_text": text,
        "is_hypothesis": False,
    }
    if exists is None:
        upsert_effect(db, ability.id, payload)
    else:
        exists.effect_text = text
        exists.turn_owner = "opponent"
        exists.timing = "end"
        exists.is_hypothesis = False


def _seed_tyranid_profiles(db) -> None:
    from app.models import TargetProfile

    rows = [
        ("Termagant", 3, 5, None, 1, None, 10, "bsdata:wh40k-11e@a566745"),
        ("Hormagaunt", 3, 5, None, 1, None, 10, "bsdata:wh40k-11e@a566745"),
        ("Tyranid Warrior", 5, 4, None, 3, None, 3, "bsdata:wh40k-11e@a566745"),
        ("Carnifex", 9, 2, None, 8, None, 1, "bsdata:wh40k-11e@a566745"),
    ]
    for name, t, save, inv, w, fnp, models, ref in rows:
        row = db.scalar(select(TargetProfile).where(TargetProfile.name == name))
        if row is None:
            db.add(
                TargetProfile(
                    name=name,
                    toughness=t,
                    save=save,
                    invuln=inv,
                    wounds=w,
                    fnp=fnp,
                    models=models,
                    keywords=[],
                    source_ref=ref,
                )
            )
        else:
            row.toughness = t
            row.save = save
            row.invuln = inv
            row.wounds = w
            row.fnp = fnp
            row.models = models
            row.source_ref = ref


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
