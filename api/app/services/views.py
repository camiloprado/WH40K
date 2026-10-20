from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from jinja2 import Environment
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import err
from app.models import (
    Ability,
    ArmyList,
    Attachment,
    Datasheet,
    Detachment,
    Enhancement,
    Faction,
    FactionRoundState,
    Game,
    GameEvent,
    GameScore,
    GameTurn,
    ListUnit,
    ListUnitModel,
    ListUnitWargear,
    ListVersion,
    ListVersionDetachment,
    MapBoard,
    MapPlacement,
    Mission,
    ObjectiveControl,
    RuleEffect,
    StratagemUse,
    TargetProfile,
    UnitState,
    Weapon,
    WeaponCheckMark,
    CpLedger,
)
from app.services.condition import validate_condition, ConditionError
from app.services.project import apply_events

PHASE_ORDER = [
    "round_start",
    "command",
    "battle_shock",
    "movement",
    "shooting",
    "charge",
    "fight",
    "end_of_turn",
    "deployment",
    "any",
]
_HTML = Environment(autoescape=True)


def _sheet_view(sheet: Datasheet | None) -> dict | None:
    if sheet is None:
        return None
    return {
        "movement": sheet.movement,
        "toughness": sheet.toughness,
        "save": sheet.save,
        "invuln": sheet.invuln,
        "wounds": sheet.wounds,
        "leadership": sheet.leadership,
        "oc": sheet.oc,
        "fnp": sheet.fnp,
        "base_size_mm": sheet.base_size_mm,
    }


def version_or_404(db: Session, version_id: int) -> ListVersion:
    row = db.get(ListVersion, version_id)
    if row is None:
        err(404, "not_found", "Versão não encontrada")
    return row


def units_for(db: Session, version_id: int) -> list[ListUnit]:
    return list(
        db.scalars(select(ListUnit).where(ListUnit.list_version_id == version_id).order_by(ListUnit.sort_order)).all()
    )


def consolidated(db: Session, version: ListVersion) -> dict:
    units = []
    total = 0
    for unit in units_for(db, version.id):
        total += unit.points
        gear = db.scalars(select(ListUnitWargear).where(ListUnitWargear.list_unit_id == unit.id)).all()
        models = db.scalars(select(ListUnitModel).where(ListUnitModel.list_unit_id == unit.id)).all()
        sheet = db.get(Datasheet, unit.datasheet_id)
        names = []
        if sheet:
            names = list(
                db.scalars(
                    select(Ability.name).where(Ability.kind == "unit", Ability.datasheet_id == sheet.id).order_by(Ability.name)
                )
            )
        units.append(
            {
                "id": unit.id,
                "datasheet_name": unit.datasheet_name,
                "datasheet_id": unit.datasheet_id,
                "export_ref": unit.export_ref,
                "model_count": unit.model_count,
                "points": unit.points,
                "enhancement_name": unit.enhancement_name,
                "enhancement_points": unit.enhancement_points,
                "is_warlord": unit.is_warlord,
                "keywords": list(sheet.keywords or []) if sheet else [],
                "stats": _sheet_view(sheet),
                "ability_names": names,
                "allows_two_leaders": bool(sheet.allows_two_leaders) if sheet else False,
                "models": [{"id": model.id, "model_name": model.model_name, "count": model.count} for model in models],
                "wargear": [
                    {"weapon_name": item.weapon_name, "count": item.count, "weapon_id": item.weapon_id}
                    for item in gear
                ],
            }
        )
    declared = version.total_points_declared
    cap = version.points_limit if version.points_limit is not None else declared
    if cap is None or total == cap:
        state = "exact"
    elif total < cap:
        state = "under"
    else:
        state = "over"
    attachments = db.scalars(select(Attachment).where(Attachment.list_version_id == version.id)).all()
    return {
        "version": _version_dict(version),
        "units": units,
        "attachments": [
            {
                "id": item.id,
                "leader_list_unit_id": item.leader_list_unit_id,
                "bodyguard_list_unit_id": item.bodyguard_list_unit_id,
                "source": item.source,
            }
            for item in attachments
        ],
        "points_sum": total,
        "points_declared": declared,
        "points_limit": version.points_limit,
        "points_state": state,
    }


def _version_dict(version: ListVersion) -> dict:
    return {
        "id": version.id,
        "list_id": version.list_id,
        "version_no": version.version_no,
        "label": version.label,
        "faction_name": version.faction_name,
        "detachment_names": list(version.detachment_names or []),
        "force_disposition": version.force_disposition,
        "battle_size": version.battle_size,
        "points_limit": version.points_limit,
        "secondaries": list(version.secondaries or []),
        "total_points_declared": version.total_points_declared,
        "points_include_enhancement": version.points_include_enhancement,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


def replace_attachments(db: Session, version: ListVersion, pairs: list[dict]) -> list[dict]:
    units = {unit.id: unit for unit in units_for(db, version.id)}
    db.execute(delete(Attachment).where(Attachment.list_version_id == version.id))
    db.flush()
    seen_leaders: set[int] = set()
    per_body: dict[int, int] = {}
    created = []
    for pair in pairs:
        leader = units.get(pair["leader_list_unit_id"])
        body = units.get(pair["bodyguard_list_unit_id"])
        if leader is None or body is None or leader.id == body.id:
            err(409, "leader_already_paired", "Par inválido", errors=[pair])
        if leader.id in seen_leaders:
            err(409, "leader_already_paired", "Líder já pareado", errors=[leader.id])
        sheet = db.get(Datasheet, body.datasheet_id)
        per_body[body.id] = per_body.get(body.id, 0) + 1
        if per_body[body.id] > 1 and not (sheet and sheet.allows_two_leaders):
            err(409, "leader_already_paired", "Bodyguard já tem líder", errors=[body.id])
        if per_body[body.id] > 2:
            err(409, "leader_already_paired", "No máximo dois líderes", errors=[body.id])
        seen_leaders.add(leader.id)
        row = Attachment(
            list_version_id=version.id,
            leader_list_unit_id=leader.id,
            bodyguard_list_unit_id=body.id,
            source="user",
        )
        db.add(row)
        db.flush()
        created.append(
            {
                "id": row.id,
                "leader_list_unit_id": leader.id,
                "bodyguard_list_unit_id": body.id,
                "source": "user",
            }
        )
    return created


def abilities_for_version(db: Session, version: ListVersion) -> list[Ability]:
    army = db.get(ArmyList, version.list_id)
    units = units_for(db, version.id)
    datasheet_ids = [unit.datasheet_id for unit in units] or [-1]
    detachment_ids = list(
        db.scalars(
            select(ListVersionDetachment.detachment_id).where(
                ListVersionDetachment.list_version_id == version.id
            )
        ).all()
    ) or [-1]
    enhancement_ids = [unit.enhancement_id for unit in units if unit.enhancement_id]
    ability_ids = []
    if enhancement_ids:
        ability_ids = [
            row
            for row in db.scalars(select(Enhancement.ability_id).where(Enhancement.id.in_(enhancement_ids))).all()
            if row
        ]
    rows = db.scalars(select(Ability)).all()
    chosen = []
    for ability in rows:
        if ability.kind in {"core", "general"}:
            chosen.append(ability)
        elif ability.kind == "faction" and army and ability.faction_id == army.faction_id:
            chosen.append(ability)
        elif ability.kind in {"detachment", "stratagem"} and ability.detachment_id in detachment_ids:
            chosen.append(ability)
        elif ability.kind == "enhancement" and (
            ability.id in ability_ids or ability.detachment_id in detachment_ids and ability.id in ability_ids
        ):
            chosen.append(ability)
        elif ability.kind in {"unit", "leader"} and ability.datasheet_id in datasheet_ids:
            chosen.append(ability)
    # enhancements ligados pelo ability_id mesmo com kind diferente
    if ability_ids:
        extra = db.scalars(select(Ability).where(Ability.id.in_(ability_ids))).all()
        ids = {item.id for item in chosen}
        chosen.extend(item for item in extra if item.id not in ids)
    return chosen


def turn_guide(db: Session, version: ListVersion, phase: str | None, turn_owner: str | None, unit_id: int | None) -> dict:
    abilities = {item.id: item for item in abilities_for_version(db, version)}
    if not abilities:
        effects = []
    else:
        effects = db.scalars(select(RuleEffect).where(RuleEffect.ability_id.in_(abilities)).order_by(RuleEffect.sort_order)).all()
    units = units_for(db, version.id)
    phases: dict[str, dict[str, list]] = {name: {"start": [], "during": [], "end": []} for name in PHASE_ORDER}
    for effect in effects:
        ability = abilities[effect.ability_id]
        if phase and effect.phase not in {phase, "any"}:
            continue
        if turn_owner and effect.turn_owner not in {turn_owner, "both"}:
            continue
        unit_ids = _effect_units(db, ability, units)
        if unit_id and unit_ids and unit_id not in unit_ids:
            continue
        phases[effect.phase][effect.timing].append(
            {
                "effect_text": effect.effect_text,
                "owner_label": effect.owner_label,
                "ability_name": ability.name,
                "effect_kind": effect.effect_kind,
                "unit_ids": unit_ids,
                "is_hypothesis": effect.is_hypothesis or ability.is_hypothesis,
                "range_in": effect.range_in,
                "choice_options": list(effect.choice_options or []),
                "choice_count": effect.choice_count,
            }
        )
    return {
        "phases": [
            {"phase": name, "groups": [{"timing": timing, "rows": rows} for timing, rows in groups.items()]}
            for name, groups in phases.items()
            if any(groups.values())
        ]
    }


def _effect_units(db: Session, ability: Ability, units: list[ListUnit]) -> list[int]:
    if ability.kind in {"unit", "leader"}:
        return [unit.id for unit in units if unit.datasheet_id == ability.datasheet_id]
    enhancement_ids = set(db.scalars(select(Enhancement.id).where(Enhancement.ability_id == ability.id)).all())
    if ability.kind == "enhancement" or enhancement_ids:
        return [unit.id for unit in units if unit.enhancement_id in enhancement_ids]
    return []


def guide_markdown(payload: dict) -> str:
    lines = ["# Turn guide", ""]
    for phase in payload["phases"]:
        lines.append(f"## {phase['phase']}")
        for group in phase["groups"]:
            if not group["rows"]:
                continue
            lines.append(f"### {group['timing']}")
            for row in group["rows"]:
                mark = " (HIPÓTESE)" if row["is_hypothesis"] else ""
                lines.append(f"- {row['effect_text']} — {row['ability_name']} ({row['owner_label']}){mark}")
        lines.append("")
    return "\n".join(lines)


def build_bundle(db: Session, version: ListVersion) -> dict:
    army = db.get(ArmyList, version.list_id)
    faction = db.get(Faction, army.faction_id) if army and army.faction_id else None
    detail = consolidated(db, version)
    abilities = abilities_for_version(db, version)
    effects = []
    if abilities:
        effects = db.scalars(select(RuleEffect).where(RuleEffect.ability_id.in_([item.id for item in abilities]))).all()
    units = units_for(db, version.id)
    owners = {item.id: _effect_units(db, item, units) for item in abilities}
    weapon_ids = [item["weapon_id"] for unit in detail["units"] for item in unit["wargear"] if item["weapon_id"]]
    weapons = db.scalars(select(Weapon).where(Weapon.id.in_(weapon_ids or [-1]))).all()
    profiles = db.scalars(select(TargetProfile)).all()
    enriched = []
    for unit in detail["units"]:
        gear = []
        for item in unit["wargear"]:
            weapon = next((row for row in weapons if row.id == item["weapon_id"]), None)
            gear.append(
                {
                    **item,
                    "keywords": list(weapon.keywords or []) if weapon else [],
                    "kind": weapon.kind if weapon else "unknown",
                    "attacks": weapon.attacks if weapon else None,
                    "skill": weapon.skill if weapon else None,
                    "strength": weapon.strength if weapon else None,
                    "ap": weapon.ap if weapon else None,
                    "damage": weapon.damage if weapon else None,
                    "range_in": weapon.range_in if weapon else None,
                    "is_stub": weapon.is_stub if weapon else True,
                }
            )
        enriched.append({**unit, "wargear": gear})
    bundle = {
        "bundle_schema_version": 1,
        "generated_at": version.created_at.isoformat() if version.created_at else None,
        "list": {
            "id": army.id if army else None,
            "name": army.name if army else "",
            "faction_id": army.faction_id if army else None,
            "accent_color": faction.accent_color.strip() if faction else "#8A8A8A",
        },
        "version": detail["version"],
        "units": enriched,
        "attachments": detail["attachments"],
        "abilities": [_ability_dict(item) for item in abilities],
        "rule_effects": [_effect_dict(item, owners.get(item.ability_id)) for item in effects],
        "weapons": [_weapon_dict(item) for item in weapons],
        "target_profiles": [
            {
                "id": item.id,
                "name": item.name,
                "toughness": item.toughness,
                "save": item.save,
                "invuln": item.invuln,
                "wounds": item.wounds,
                "fnp": item.fnp,
                "models": item.models,
                "keywords": list(item.keywords or []),
            }
            for item in profiles
        ],
    }
    return bundle


def bundle_etag(bundle: dict) -> str:
    payload = {key: value for key, value in bundle.items() if key != "generated_at"}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return '"' + hashlib.sha256(raw.encode()).hexdigest() + '"'


def diff_versions(db: Session, left_id: int, right_id: int) -> dict:
    left = consolidated(db, version_or_404(db, left_id))
    right = consolidated(db, version_or_404(db, right_id))
    left_units = _bucket(left["units"])
    right_units = _bucket(right["units"])
    added, removed, changed = [], [], []
    for key, rows in right_units.items():
        previous = left_units.get(key, [])
        if not previous:
            added.extend(rows)
            continue
        for index, row in enumerate(rows):
            if index >= len(previous):
                added.append(row)
                continue
            fields = []
            for field in ("points", "model_count", "enhancement_name", "is_warlord"):
                if previous[index][field] != row[field]:
                    fields.append({"field": field, "before": previous[index][field], "after": row[field]})
            before_gear = [item["weapon_name"] for item in previous[index]["wargear"]]
            after_gear = [item["weapon_name"] for item in row["wargear"]]
            if before_gear != after_gear:
                fields.append({"field": "wargear", "before": before_gear, "after": after_gear})
            if fields:
                changed.append({"name": row["datasheet_name"], "fields": fields})
    for key, rows in left_units.items():
        extra = len(rows) - len(right_units.get(key, []))
        if extra > 0:
            removed.extend(rows[-extra:])
    return {
        "left": left["version"],
        "right": right["version"],
        "points": {"left": left["points_sum"], "right": right["points_sum"]},
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def _bucket(units: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {}
    for unit in units:
        buckets.setdefault(unit["datasheet_name"], []).append(unit)
    return buckets


def render_map_html(name: str, placements: list[dict]) -> str:
    template = _HTML.from_string(
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>{{ name }}</title></head>"
        "<body><h1>{{ name }}</h1><ul>"
        "{% for item in placements %}<li>{{ item.unit }} — {{ item.x }}, {{ item.y }} ({{ item.state }})</li>{% endfor %}"
        "</ul></body></html>"
    )
    return template.render(name=name, placements=placements)


def sync_events(db: Session, game_id: uuid.UUID, events: list[dict]) -> dict:
    game = db.get(Game, game_id)
    if game is None:
        err(404, "not_found", "Partida não encontrada")
    accepted, duplicates = [], []
    for item in events:
        payload = item["payload"]
        encoded = json.dumps(payload)
        if len(encoded.encode()) > 8192:
            err(413, "payload_too_large", "Evento grande demais")
        created = _parse_time(item["created_at"])
        row = GameEvent(
            id=uuid.UUID(item["id"]),
            game_id=game_id,
            seq=item["seq"],
            device_id=item["device_id"][:64],
            type=item["type"],
            payload=payload,
            undoes_event_id=uuid.UUID(item["undoes_event_id"]) if item.get("undoes_event_id") else None,
            created_at=created,
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
            accepted.append(item["id"])
        except IntegrityError:
            duplicates.append(item["id"])
    _rebuild(db, game)
    last = db.scalar(select(func.max(GameEvent.seq)).where(GameEvent.game_id == game_id)) or 0
    return {"accepted": accepted, "duplicates": duplicates, "last_seq": last}


def _rebuild(db: Session, game: Game) -> None:
    rows = db.scalars(select(GameEvent).where(GameEvent.game_id == game.id)).all()
    events = [
        {
            "id": str(row.id),
            "seq": row.seq,
            "device_id": row.device_id,
            "type": row.type,
            "payload": row.payload,
            "undoes_event_id": str(row.undoes_event_id) if row.undoes_event_id else None,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
    state = apply_events(events)
    for model in (
        FactionRoundState,
        GameScore,
        ObjectiveControl,
        CpLedger,
        StratagemUse,
        UnitState,
        GameTurn,
    ):
        db.execute(delete(model).where(model.game_id == game.id))
    db.flush()
    game.status = state["status"] if state["status"] in {"active", "finished", "abandoned"} else game.status
    if state.get("result") in {"win", "loss", "draw"}:
        game.result = state["result"]
    if state.get("list_label"):
        game.list_label = state["list_label"]
    game.current_round = state["round"]
    game.current_player = state["player"] if state["player"] in {"me", "opponent"} else game.current_player
    game.current_phase = state["phase"]
    game.cp_me = max(0, min(99, int(state["cp"]["me"] or 0)))
    game.cp_opponent = max(0, min(99, int(state["cp"]["opponent"] or 0)))
    game.vp_me = int(state["vp"]["me"])
    game.vp_opponent = int(state["vp"]["opponent"])
    game.last_seq = len(rows)
    for turn in state["turns"]:
        db.add(
            GameTurn(
                id=uuid.uuid4(),
                game_id=game.id,
                round=turn["round"],
                player=turn["player"],
                phase=turn["phase"],
                started_at=_parse_time(turn["started_at"]),
                ended_at=_parse_time(turn["ended_at"]) if turn["ended_at"] else None,
            )
        )
    for unit in state["unit_states"]:
        if game.list_version_id is None:
            continue
        db.add(
            UnitState(
                id=uuid.uuid4(),
                game_id=game.id,
                list_version_id=game.list_version_id,
                list_unit_id=unit["list_unit_id"],
                round=unit["round"],
                player="me",
                moved=unit["moved"],
                shot=bool(unit["shot"]),
                charged=bool(unit["charged"]),
                fought=bool(unit["fought"]),
                engaged=bool(unit["engaged"]),
                on_action=bool(unit["on_action"]),
                action_name=unit["action_name"],
                battle_shocked=bool(unit["battle_shocked"]),
                below_half=bool(unit["below_half"]),
                destroyed=bool(unit["destroyed"]),
                in_reserves=bool(unit["in_reserves"]),
                lane=unit["lane"],
                overrides=unit["overrides"],
            )
        )
    for item in state["stratagem_uses"]:
        db.add(
            StratagemUse(
                id=uuid.UUID(item["id"]),
                game_id=game.id,
                ability_id=item["ability_id"],
                stratagem_name=item["stratagem_name"][:200],
                round=item["round"],
                player=item["player"],
                phase=item["phase"],
                cp_spent=max(0, min(5, int(item["cp_spent"]))),
                target_list_unit_id=None if game.list_version_id is None else item["target_list_unit_id"],
                limit_overridden=item["limit_overridden"],
                created_at=_parse_time(item["created_at"]),
            )
        )
    for item in state["ledger"]:
        db.add(
            CpLedger(
                id=uuid.UUID(item["id"]),
                game_id=game.id,
                round=item["round"],
                player=item["player"],
                phase=item["phase"],
                delta=max(-10, min(10, int(item["delta"]))),
                reason=item["reason"],
                stratagem_use_id=uuid.UUID(item["stratagem_use_id"]) if item["stratagem_use_id"] else None,
                created_at=_parse_time(item["created_at"]),
            )
        )
    for item in state["objectives"]:
        db.add(
            ObjectiveControl(
                id=uuid.uuid4(),
                game_id=game.id,
                round=item["round"],
                player_turn=item["player_turn"],
                objective_label=item["objective_label"],
                controller=item["controller"],
            )
        )
    for item in state["scores"]:
        db.add(
            GameScore(
                id=uuid.uuid4(),
                game_id=game.id,
                round=item["round"],
                player=item["player"],
                kind=item["kind"],
                label=item["label"],
                vp=max(-50, min(50, int(item["vp"]))),
                created_at=_parse_time(item["created_at"]),
            )
        )
    for item in state["shadow"]:
        db.add(
            FactionRoundState(
                id=uuid.uuid4(),
                game_id=game.id,
                round=item["round"],
                player=item["player"],
                state_key="shadow_of_chaos",
                objectives_controlled=item["objectives_controlled"],
                whole_board=item["whole_board"],
                value=item["value"],
            )
        )


def game_detail(db: Session, game: Game) -> dict:
    def rows(model):
        return db.scalars(select(model).where(model.game_id == game.id)).all()

    return {
        "id": str(game.id),
        "list_version_id": game.list_version_id,
        "bundle_etag": game.bundle_etag,
        "opponent_name": game.opponent_name,
        "opponent_faction": game.opponent_faction,
        "mission_name": game.mission_name,
        "first_player": game.first_player,
        "status": game.status,
        "result": game.result,
        "list_label": game.list_label,
        "current_round": game.current_round,
        "current_player": game.current_player,
        "current_phase": game.current_phase,
        "cp_me": game.cp_me,
        "cp_opponent": game.cp_opponent,
        "vp_me": game.vp_me,
        "vp_opponent": game.vp_opponent,
        "last_seq": game.last_seq,
        "turns": [
            {"round": item.round, "player": item.player, "phase": item.phase}
            for item in rows(GameTurn)
        ],
        "unit_states": [
            {
                "list_unit_id": item.list_unit_id,
                "round": item.round,
                "player": item.player,
                "moved": item.moved,
                "shot": item.shot,
                "charged": item.charged,
                "fought": item.fought,
                "engaged": item.engaged,
                "on_action": item.on_action,
                "battle_shocked": item.battle_shocked,
                "destroyed": item.destroyed,
                "in_reserves": item.in_reserves,
                "lane": item.lane,
                "overrides": item.overrides,
            }
            for item in rows(UnitState)
        ],
        "stratagem_uses": [
            {
                "stratagem_name": item.stratagem_name,
                "cp_spent": item.cp_spent,
                "phase": item.phase,
                "limit_overridden": item.limit_overridden,
            }
            for item in rows(StratagemUse)
        ],
        "objectives": [
            {
                "round": item.round,
                "objective_label": item.objective_label,
                "controller": item.controller,
            }
            for item in rows(ObjectiveControl)
        ],
        "scores": [
            {"round": item.round, "player": item.player, "kind": item.kind, "label": item.label, "vp": item.vp}
            for item in rows(GameScore)
        ],
        "shadow": [
            {
                "round": item.round,
                "player": item.player,
                "objectives_controlled": item.objectives_controlled,
                "whole_board": item.whole_board,
            }
            for item in rows(FactionRoundState)
        ],
    }


def upsert_effect(db: Session, ability_id: int, payload: dict) -> RuleEffect:
    try:
        validate_condition(payload.get("condition_json") or {})
    except ConditionError as exc:
        err(422, "validation_error", str(exc))
    if payload.get("effect_kind") in {"allow", "deny"} and not payload.get("restriction_key"):
        err(422, "validation_error", "allow/deny exigem restriction_key")
    options, count, scope = clean_choice(payload)
    row = RuleEffect(
        choice_options=options,
        choice_count=count,
        choice_scope=scope,
        ability_id=ability_id,
        phase=payload["phase"],
        turn_owner=payload.get("turn_owner") or "own",
        timing=payload.get("timing") or "during",
        effect_kind=payload.get("effect_kind") or "reminder",
        restriction_key=payload.get("restriction_key"),
        condition_json=payload.get("condition_json") or {},
        owner_label=payload["owner_label"][:200],
        effect_text=payload["effect_text"][:4000],
        range_in=payload.get("range_in"),
        sort_order=payload.get("sort_order") or 0,
        is_hypothesis=bool(payload.get("is_hypothesis")),
    )
    db.add(row)
    db.flush()
    return row


def clean_choice(payload: dict) -> tuple[list[str], int | None, str]:
    raw = payload.get("choice_options") or []
    if not isinstance(raw, list) or len(raw) > 12:
        err(422, "validation_error", "No máximo 12 opções")
    options = [str(item).strip()[:200] for item in raw if str(item).strip()]
    count = payload.get("choice_count")
    if options:
        count = int(count or 1)
        if not 1 <= count <= min(6, len(options)):
            err(422, "validation_error", "Quantidade de escolhas inválida")
    else:
        count = None
    scope = payload.get("choice_scope") or "turn"
    if scope not in {"turn", "round", "battle"}:
        err(422, "validation_error", "Escopo de escolha inválido")
    return options, count, scope


def _ability_dict(item: Ability) -> dict:
    return {
        "id": item.id,
        "kind": item.kind,
        "faction_id": item.faction_id,
        "datasheet_id": item.datasheet_id,
        "detachment_id": item.detachment_id,
        "name": item.name,
        "cp_cost": item.cp_cost,
        "use_limit": item.use_limit,
        "usable_turn": item.usable_turn,
        "summary_user": item.summary_user,
        "is_hypothesis": item.is_hypothesis,
    }


def _effect_dict(item: RuleEffect, unit_ids: list[int] | None = None) -> dict:
    return {
        "id": item.id,
        "unit_ids": unit_ids or [],
        "choice_options": list(item.choice_options or []),
        "choice_count": item.choice_count,
        "choice_scope": item.choice_scope or "turn",
        "ability_id": item.ability_id,
        "phase": item.phase,
        "turn_owner": item.turn_owner,
        "timing": item.timing,
        "effect_kind": item.effect_kind,
        "restriction_key": item.restriction_key,
        "condition_json": item.condition_json,
        "owner_label": item.owner_label,
        "effect_text": item.effect_text,
        "range_in": item.range_in,
        "is_hypothesis": item.is_hypothesis,
    }


def _weapon_dict(item: Weapon) -> dict:
    return {
        "id": item.id,
        "datasheet_id": item.datasheet_id,
        "name": item.name,
        "kind": item.kind,
        "range_in": item.range_in,
        "attacks": item.attacks,
        "skill": item.skill,
        "strength": item.strength,
        "ap": item.ap,
        "damage": item.damage,
        "keywords": list(item.keywords or []),
        "is_stub": item.is_stub,
    }


def _parse_time(value: str) -> datetime:
    if isinstance(value, datetime):
        return value
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def map_dict(board: MapBoard, placements: list[MapPlacement], units: dict[int, ListUnit]) -> dict:
    return {
        "id": board.id,
        "list_version_id": board.list_version_id,
        "mission_id": board.mission_id,
        "name": board.name,
        "side": board.side,
        "terrain_json": board.terrain_json,
        "notes": board.notes,
        "placements": [
            {
                "id": item.id,
                "list_unit_id": item.list_unit_id,
                "unit": units[item.list_unit_id].datasheet_name if item.list_unit_id in units else "",
                "x": float(item.x_in) if isinstance(item.x_in, Decimal) else item.x_in,
                "y": float(item.y_in) if isinstance(item.y_in, Decimal) else item.y_in,
                "rotation_deg": float(item.rotation_deg) if item.rotation_deg is not None else 0,
                "state": item.state,
                "first_target": item.first_target,
            }
            for item in placements
        ],
    }
