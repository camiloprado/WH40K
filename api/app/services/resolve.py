from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.errors import err
from app.models import (
    ArmyList,
    Attachment,
    Ability,
    Datasheet,
    Detachment,
    Enhancement,
    Faction,
    ImportRow,
    ListUnit,
    ListUnitModel,
    ListUnitWargear,
    ListVersion,
    ListVersionDetachment,
    Weapon,
)
from app.services.parse import parse
from app.services.parse.models import ParseResult, ParsedUnit, ParsedWargear
from app.services.parse.normalize import MAX_BYTES, utf8_len, normalize_input

STUB_LIMIT = 100


class _Stubs:
    def __init__(self) -> None:
        self.count = 0

    def bump(self) -> None:
        self.count += 1
        if self.count > STUB_LIMIT:
            err(400, "invalid_input", "Limite de 100 stubs por import")


def commit_import(db: Session, raw_text: str, target: dict, resolutions: dict, expected_hash: str) -> dict:
    normalized = normalize_input(raw_text)
    if utf8_len(normalized) > MAX_BYTES or utf8_len(raw_text) > MAX_BYTES:
        err(413, "payload_too_large", "Texto grande demais")
    parsed = parse(raw_text)
    if parsed.parse_hash != expected_hash:
        err(409, "parse_changed", "O texto mudou desde o preview")
    faction_name = (resolutions.get("faction_name") or parsed.header.faction_name or "").strip()
    if not faction_name:
        err(400, "invalid_input", "Escolha a facção")
    stubs = _Stubs()
    faction = _faction(db, faction_name[:200], stubs)
    army = _lock_list(db, target, faction)
    version_no = db.scalar(select(func.max(ListVersion.version_no)).where(ListVersion.list_id == army.id)) or 0
    warnings = [item.model_dump() for item in parsed.warnings]
    imported = ImportRow(
        list_id=army.id,
        raw_text=raw_text,
        input_format=parsed.format,
        parser_version=parsed.parser_version,
        parse_hash=parsed.parse_hash,
        generator=parsed.generator,
        parsed_json=parsed.model_dump(mode="json"),
        warnings=warnings,
    )
    db.add(imported)
    db.flush()
    names = [
        item.name if not item.variant else f"{item.name} ({item.variant})" for item in parsed.header.detachments
    ]
    version = ListVersion(
        list_id=army.id,
        version_no=int(version_no) + 1,
        import_id=imported.id,
        faction_name=faction.name,
        detachment_names=names,
        force_disposition=parsed.header.force_disposition,
        battle_size=parsed.header.battle_size,
        points_limit=parsed.header.points_limit,
        secondaries=parsed.header.secondaries,
        total_points_declared=parsed.header.total_points_declared,
        points_include_enhancement=parsed.header.points_include_enhancement,
    )
    db.add(version)
    db.flush()
    detachments = [
        _detachment(db, faction.id, item.name, item.variant, stubs) for item in parsed.header.detachments
    ]
    if not detachments:
        detachments = [_detachment(db, faction.id, "Sem detachment", None, stubs)]
    for item in detachments:
        db.add(ListVersionDetachment(list_version_id=version.id, detachment_id=item.id))
    by_line: dict[int, ListUnit] = {}
    by_path: dict[str, ListUnit] = {}
    seen_refs: set[str] = set()
    warlord_set = False
    for index, unit in enumerate(parsed.units):
        export_ref = unit.export_ref
        if export_ref and export_ref in seen_refs:
            warnings.append({"reason": "duplicate_export_ref", "text": export_ref})
            export_ref = None
        if export_ref:
            seen_refs.add(export_ref)
        is_warlord = unit.is_warlord
        if is_warlord and warlord_set:
            warnings.append({"reason": "extra_warlord", "text": unit.name})
            is_warlord = False
        warlord_set = warlord_set or is_warlord
        sheet = _datasheet(db, faction.id, unit, stubs)
        enhancement_id = None
        if unit.enhancement_name:
            enhancement_id = _enhancement(db, detachments[0].id, unit, stubs).id
        row = ListUnit(
            list_version_id=version.id,
            datasheet_name=unit.name[:200],
            datasheet_id=sheet.id,
            export_ref=export_ref,
            model_count=max(1, min(unit.model_count, 200)),
            points=max(0, min(unit.points, 10000)),
            enhancement_name=unit.enhancement_name,
            enhancement_points=unit.enhancement_points,
            enhancement_id=enhancement_id,
            is_warlord=is_warlord,
            sort_order=index,
        )
        db.add(row)
        db.flush()
        _gear(db, row, unit, sheet, stubs)
        if unit.line_no is not None:
            by_line[unit.line_no] = row
        if unit.json_path:
            by_path[unit.json_path] = row
    choices = resolutions.get("leader_pairs") or []
    pairs = choices or [item.model_dump() for item in parsed.leader_pairs]
    for pair in pairs:
        leader = _pick(by_line, by_path, pair.get("leader_line"), pair.get("leader_path"))
        body = _pick(by_line, by_path, pair.get("bodyguard_line"), pair.get("bodyguard_path"))
        if leader is None or body is None or leader.id == body.id:
            warnings.append({"reason": "leader_unresolved", "text": str(pair)})
            continue
        if not _can_attach(db, body):
            warnings.append({"reason": "leader_already_paired", "text": body.datasheet_name})
            continue
        db.add(
            Attachment(
                list_version_id=version.id,
                leader_list_unit_id=leader.id,
                bodyguard_list_unit_id=body.id,
                source="import" if not choices else "user",
            )
        )
    imported.warnings = warnings
    army.current_version_id = version.id
    army.faction_id = faction.id
    db.flush()
    return {
        "list_id": army.id,
        "version_id": version.id,
        "version_no": version.version_no,
        "warnings": warnings,
    }


def _lock_list(db: Session, target: dict, faction: Faction) -> ArmyList:
    list_id = target.get("list_id")
    if list_id:
        db.execute(text("SELECT id FROM lists WHERE id = :id FOR UPDATE"), {"id": list_id})
        army = db.get(ArmyList, list_id)
        if army is None:
            err(404, "not_found", "Lista não encontrada")
        return army
    name = (target.get("new_list_name") or faction.name)[:200]
    army = ArmyList(name=name, faction_id=faction.id, archived=False)
    db.add(army)
    db.flush()
    db.execute(text("SELECT id FROM lists WHERE id = :id FOR UPDATE"), {"id": army.id})
    return army


def _pick(by_line, by_path, line, path):
    if line is not None and line in by_line:
        return by_line[line]
    if path and path in by_path:
        return by_path[path]
    return None


def _can_attach(db: Session, body: ListUnit) -> bool:
    rows = db.scalars(select(Attachment).where(Attachment.bodyguard_list_unit_id == body.id)).all()
    if not rows:
        return True
    sheet = db.get(Datasheet, body.datasheet_id)
    return bool(sheet and sheet.allows_two_leaders and len(rows) < 2)


def _faction(db: Session, name: str, stubs: _Stubs) -> Faction:
    row = db.scalar(select(Faction).where(Faction.name == name))
    if row:
        return row
    stubs.bump()
    row = Faction(name=name, source="import", accent_color="#8A8A8A")
    db.add(row)
    db.flush()
    return row


def _detachment(db: Session, faction_id: int, name: str, variant: str | None, stubs: _Stubs) -> Detachment:
    row = db.scalar(
        select(Detachment).where(
            Detachment.faction_id == faction_id,
            Detachment.name == name,
            Detachment.variant.is_(None) if variant is None else Detachment.variant == variant,
        )
    )
    if row:
        return row
    stubs.bump()
    row = Detachment(faction_id=faction_id, name=name[:200], variant=variant, source="import")
    db.add(row)
    db.flush()
    return row


SHEET_NUMBERS = ("movement", "toughness", "save", "invuln", "wounds", "leadership", "oc", "fnp")


def _datasheet(db: Session, faction_id: int, unit: ParsedUnit, stubs: _Stubs) -> Datasheet:
    row = db.scalar(select(Datasheet).where(Datasheet.faction_id == faction_id, Datasheet.name == unit.name[:200]))
    if row:
        if row.source != "user":
            _fill_sheet(row, unit)
        _abilities(db, row, unit)
        return row
    stubs.bump()
    row = Datasheet(
        faction_id=faction_id,
        name=unit.name[:200],
        keywords=unit.keywords[:50],
        is_character=unit.is_character,
        is_stub=True,
        source="import",
    )
    _fill_sheet(row, unit)
    db.add(row)
    db.flush()
    _abilities(db, row, unit)
    return row


def _fill_sheet(row: Datasheet, unit: ParsedUnit) -> None:
    for key in SHEET_NUMBERS:
        if getattr(row, key) is None and getattr(unit, key) is not None:
            setattr(row, key, getattr(unit, key))
    if not row.base_size_mm and unit.base_size_mm:
        row.base_size_mm = unit.base_size_mm
    if not row.keywords and unit.keywords:
        row.keywords = unit.keywords[:50]
    if row.is_character is False and unit.is_character:
        row.is_character = True
    if row.toughness is not None or row.wounds is not None:
        row.is_stub = False


def _abilities(db: Session, sheet: Datasheet, unit: ParsedUnit) -> None:
    if not sheet.id or not unit.ability_names:
        return
    existing = set(
        db.scalars(
            select(Ability.name).where(Ability.kind == "unit", Ability.datasheet_id == sheet.id, Ability.name.in_(unit.ability_names))
        )
    )
    for name in unit.ability_names:
        if name in existing:
            continue
        db.add(Ability(kind="unit", datasheet_id=sheet.id, name=name, is_hypothesis=True, source="import"))


def _enhancement(db: Session, detachment_id: int, unit: ParsedUnit, stubs: _Stubs) -> Enhancement:
    name = (unit.enhancement_name or "")[:200]
    row = db.scalar(select(Enhancement).where(Enhancement.detachment_id == detachment_id, Enhancement.name == name))
    if row:
        return row
    stubs.bump()
    row = Enhancement(detachment_id=detachment_id, name=name, points=unit.enhancement_points or 0)
    db.add(row)
    db.flush()
    return row


def _gear(db: Session, row: ListUnit, unit: ParsedUnit, sheet: Datasheet, stubs: _Stubs) -> None:
    for item in unit.wargear:
        _one_gear(db, row, None, item, sheet, stubs)
    for model in unit.models:
        model_row = ListUnitModel(list_unit_id=row.id, model_name=model.name[:200], count=max(1, min(model.count, 200)))
        db.add(model_row)
        db.flush()
        for item in model.wargear:
            _one_gear(db, row, model_row.id, item, sheet, stubs)


def _one_gear(db, row: ListUnit, model_id: int | None, item: ParsedWargear, sheet: Datasheet, stubs: _Stubs) -> None:
    weapon = db.scalar(select(Weapon).where(Weapon.datasheet_id == sheet.id, Weapon.name == item.name[:200]))
    if weapon is None:
        stubs.bump()
        stats = item.stats
        weapon = Weapon(
            datasheet_id=sheet.id,
            name=item.name[:200],
            kind=stats.kind if stats else "wargear",
            range_in=stats.range_in if stats else None,
            attacks=stats.attacks if stats else None,
            skill=stats.skill if stats else None,
            strength=stats.strength if stats else None,
            ap=stats.ap if stats else None,
            damage=stats.damage if stats else None,
            keywords=(stats.keywords if stats else [])[:50],
            is_stub=not bool(stats and (stats.strength or stats.damage or stats.attacks)),
            source="import",
        )
        db.add(weapon)
        db.flush()
    db.add(
        ListUnitWargear(
            list_unit_id=row.id,
            list_unit_model_id=model_id,
            weapon_name=item.name[:200],
            weapon_id=weapon.id,
            count=max(1, item.count),
        )
    )


def preview(raw_text: str, format_hint: str | None) -> ParseResult:
    normalized = normalize_input(raw_text)
    if utf8_len(normalized) > MAX_BYTES:
        err(413, "payload_too_large", "Texto grande demais")
    return parse(raw_text, format_hint)
