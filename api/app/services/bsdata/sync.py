"""Compara o esqueleto BSData com o catálogo local e, se pedido, aplica.

Nunca apaga nada, nunca mexe em summary_user nem em efeitos que já existem,
e não sobrescreve ficha ou arma que o usuário editou à mão.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import err
from app.models import Ability, BsdataImport, Datasheet, Detachment, Enhancement, Faction, RuleEffect, Weapon
from app.services.bsdata.parse import ParsedAbility, ParsedFaction

PLACEHOLDER = "Resumo pendente: confira no codex e escreva com suas palavras no Catálogo."
SHEET_FIELDS = ("movement", "toughness", "save", "invuln", "wounds", "leadership", "oc")
WEAPON_FIELDS = ("kind", "range_in", "attacks", "skill", "strength", "ap", "damage", "keywords")
CATEGORIES = ("datasheets", "weapons", "abilities", "effects", "detachments", "enhancements")
LIST_CAP = 400


def faction_name(catalogue: str) -> str:
    return catalogue[:-5] if catalogue.endswith(".json") else catalogue


class _Report:
    def __init__(self) -> None:
        self.data = {name: {"added": [], "changed": [], "kept": []} for name in CATEGORIES}
        self.counts = {name: {"added": 0, "changed": 0, "kept": 0, "same": 0} for name in CATEGORIES}

    def add(self, category: str, bucket: str, item) -> None:
        self.counts[category][bucket] += 1
        if bucket == "same":
            return
        items = self.data[category][bucket]
        if len(items) < LIST_CAP:
            items.append(item)


class _Sync:
    def __init__(self, db: Session, parsed: ParsedFaction, faction: Faction | None, apply: bool):
        self.db = db
        self.parsed = parsed
        self.faction = faction
        self.apply = apply
        self.report = _Report()
        fid = faction.id if faction else None
        self.sheets = {row.name: row for row in db.scalars(select(Datasheet).where(Datasheet.faction_id == fid))} if fid else {}
        self.detachments: dict[str, Detachment] = {}
        if fid:
            for row in db.scalars(select(Detachment).where(Detachment.faction_id == fid).order_by(Detachment.id)):
                self.detachments.setdefault(row.name, row)
        self.abilities: dict[tuple, Ability] = {}
        self.with_effects: set[int] = set()
        if fid:
            sheet_ids = [row.id for row in self.sheets.values()]
            det_ids = [row.id for row in self.detachments.values()]
            query = select(Ability).where(
                (Ability.faction_id == fid) | Ability.datasheet_id.in_(sheet_ids or [0]) | Ability.detachment_id.in_(det_ids or [0])
            )
            for row in db.scalars(query):
                self.abilities[(row.kind, row.faction_id, row.datasheet_id, row.detachment_id, row.name)] = row
            ids = [row.id for row in self.abilities.values()]
            self.with_effects = set(db.scalars(select(RuleEffect.ability_id).where(RuleEffect.ability_id.in_(ids or [0]))))

    def run(self) -> dict:
        for unit in self.parsed.units:
            sheet = self._sheet(unit)
            self._weapons(unit, sheet)
            for ability in unit.abilities:
                self._ability("unit", ability, unit.name, datasheet_id=sheet.id if sheet else None)
        for rule in self.parsed.faction_rules:
            self._ability("faction", rule, faction_name(self.parsed.catalogue), faction_id=self.faction.id if self.faction else None)
        for parsed in self.parsed.detachments:
            detachment = self._detachment(parsed)
            det_id = detachment.id if detachment else None
            for rule in parsed.rules:
                self._ability("detachment", rule, parsed.name, detachment_id=det_id)
            for item in parsed.enhancements:
                ability = self._ability("enhancement", item.ability, item.name, detachment_id=det_id)
                self._enhancement(item, detachment, ability)
        if self.apply:
            self.db.flush()
        return self.report

    def _sheet(self, unit) -> Datasheet | None:
        row = self.sheets.get(unit.name)
        values = {key: unit.stats.get(key) for key in SHEET_FIELDS}
        values["keywords"] = unit.keywords
        values["is_character"] = unit.is_character
        if row is None:
            self.report.add("datasheets", "added", unit.name)
            if not self.apply:
                return None
            row = Datasheet(faction_id=self.faction.id, name=unit.name, is_stub=False, source="bsdata", source_ref=unit.ref, **values)
            self.db.add(row)
            self.db.flush()
            self.sheets[unit.name] = row
            return row
        changes = [key for key, value in values.items() if value is not None and getattr(row, key) != value]
        editable = row.is_stub or row.source in {"import", "bsdata"}
        if not changes:
            self.report.add("datasheets", "same", unit.name)
        else:
            self.report.add("datasheets", "changed" if editable else "kept", {"name": unit.name, "fields": changes})
        if self.apply and editable:
            for key in changes:
                setattr(row, key, values[key])
            row.is_stub = False
            row.source = "bsdata"
            row.source_ref = unit.ref[:300]
        return row

    def _weapons(self, unit, sheet: Datasheet | None) -> None:
        existing = {}
        if sheet is not None and sheet.id:
            existing = {row.name: row for row in self.db.scalars(select(Weapon).where(Weapon.datasheet_id == sheet.id))}
        for weapon in unit.weapons:
            label = f"{unit.name} · {weapon['name']}"
            row = existing.get(weapon["name"])
            if row is None:
                self.report.add("weapons", "added", label)
                if self.apply and sheet is not None:
                    self.db.add(Weapon(datasheet_id=sheet.id, is_stub=False, source="bsdata", **weapon))
                continue
            changes = [key for key in WEAPON_FIELDS if weapon[key] is not None and getattr(row, key) != weapon[key]]
            editable = row.is_stub or row.source in {"import", "bsdata"}
            if not changes:
                self.report.add("weapons", "same", label)
                continue
            self.report.add("weapons", "changed" if editable else "kept", {"name": label, "fields": changes})
            if self.apply and editable:
                for key in changes:
                    setattr(row, key, weapon[key])
                row.is_stub = False
                row.source = "bsdata"

    def _detachment(self, parsed) -> Detachment | None:
        row = self.detachments.get(parsed.name)
        if row is not None:
            self.report.add("detachments", "same", parsed.name)
            if self.apply and row.source_ref is None:
                row.source_ref = parsed.ref[:300]
            return row
        self.report.add("detachments", "added", parsed.name)
        if not self.apply:
            return None
        row = Detachment(faction_id=self.faction.id, name=parsed.name, source="bsdata", source_ref=parsed.ref[:300])
        self.db.add(row)
        self.db.flush()
        self.detachments[parsed.name] = row
        return row

    def _ability(self, kind: str, parsed: ParsedAbility, owner: str, faction_id=None, datasheet_id=None, detachment_id=None) -> Ability | None:
        key = (kind, faction_id, datasheet_id, detachment_id, parsed.name)
        owned = any(value is not None for value in key[1:4])
        row = self.abilities.get(key) if owned else None
        label = f"{owner} · {parsed.name}"
        if row is None:
            self.report.add("abilities", "added", label)
            if self.apply and owned:
                row = Ability(
                    kind=kind,
                    faction_id=faction_id,
                    datasheet_id=datasheet_id,
                    detachment_id=detachment_id,
                    name=parsed.name,
                    is_hypothesis=True,
                    source="bsdata",
                    source_ref=parsed.ref[:300],
                )
                self.db.add(row)
                self.db.flush()
                self.abilities[key] = row
        else:
            self.report.add("abilities", "same", label)
        if parsed.guess is None or (row is not None and row.id in self.with_effects):
            return row
        self.report.add("effects", "added", {"name": label, "phase": parsed.guess.phase, "options": len(parsed.options), "count": parsed.count})
        if self.apply and row is not None:
            has_choice = bool(parsed.options)
            self.db.add(
                RuleEffect(
                    ability_id=row.id,
                    phase=parsed.guess.phase,
                    turn_owner=parsed.guess.turn_owner,
                    timing=parsed.guess.timing,
                    effect_kind="prompt" if has_choice else "reminder",
                    owner_label=owner[:200],
                    effect_text=PLACEHOLDER,
                    is_hypothesis=True,
                    choice_options=parsed.options if has_choice else [],
                    choice_count=parsed.count if has_choice else None,
                    choice_scope=parsed.scope,
                    source="bsdata",
                )
            )
            self.with_effects.add(row.id)
        return row

    def _enhancement(self, parsed, detachment: Detachment | None, ability: Ability | None) -> None:
        row = None
        if detachment is not None and detachment.id:
            row = self.db.scalar(
                select(Enhancement).where(Enhancement.detachment_id == detachment.id, Enhancement.name == parsed.name)
            )
        label = f"{detachment.name if detachment else '?'} · {parsed.name}"
        if row is None:
            self.report.add("enhancements", "added", {"name": label, "points": parsed.points})
            if self.apply and detachment is not None:
                self.db.add(
                    Enhancement(
                        detachment_id=detachment.id,
                        name=parsed.name,
                        points=parsed.points,
                        ability_id=ability.id if ability else None,
                        source="bsdata",
                        source_ref=parsed.ref[:300],
                    )
                )
            return
        if parsed.points is not None and row.points != parsed.points:
            self.report.add("enhancements", "changed", {"name": label, "fields": ["points"], "from": row.points, "to": parsed.points})
            if self.apply:
                row.points = parsed.points
        else:
            self.report.add("enhancements", "same", label)
        if self.apply and row.ability_id is None and ability is not None:
            row.ability_id = ability.id


def find_faction(db: Session, catalogue: str, faction_id: int | None) -> Faction | None:
    if faction_id:
        row = db.get(Faction, faction_id)
        if row is None:
            err(404, "not_found", "Facção não encontrada")
        return row
    name = faction_name(catalogue)
    row = db.scalar(select(Faction).where(Faction.name == name))
    if row is None and " - " in name:
        row = db.scalar(select(Faction).where(Faction.name == name.split(" - ", 1)[1]))
    return row


def sync(db: Session, parsed: ParsedFaction, repo: str, sha: str, faction_id: int | None, apply: bool) -> dict:
    faction = find_faction(db, parsed.catalogue, faction_id)
    created = False
    if faction is None and apply:
        faction = Faction(name=faction_name(parsed.catalogue)[:200], source="bsdata", source_ref=f"{repo}/{parsed.catalogue}"[:300])
        db.add(faction)
        db.flush()
        created = True
    report = _Sync(db, parsed, faction, apply).run()
    result = {
        "repo": repo,
        "sha": sha,
        "catalogue": parsed.catalogue,
        "revision": parsed.revision,
        "faction": {"id": faction.id, "name": faction.name, "created": created} if faction else {"id": None, "name": faction_name(parsed.catalogue), "created": False},
        "applied": apply,
        "changes": report.data,
        "counts": report.counts,
    }
    if apply:
        db.add(
            BsdataImport(
                repo=repo,
                sha=sha,
                catalogue=parsed.catalogue[:200],
                revision=parsed.revision,
                faction_id=faction.id,
                summary={"counts": result["counts"]},
            )
        )
        db.flush()
    return result
