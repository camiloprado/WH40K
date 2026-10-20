from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import err
from app.models import Ability, RuleEffect
from app.services.views import upsert_effect, version_or_404

_PHASES = [
    ("battle_shock", re.compile(r"battle[\s-]?shock|choque", re.I)),
    ("end_of_turn", re.compile(r"end of turn|fim de turno|^fim$", re.I)),
    ("command", re.compile(r"command|comando", re.I)),
    ("movement", re.compile(r"movement|movimento", re.I)),
    ("shooting", re.compile(r"shooting|tiro|disparo", re.I)),
    ("charge", re.compile(r"^charge\b|carga", re.I)),
    ("fight", re.compile(r"fight|combate|luta", re.I)),
]


def parse_cheatsheet(text: str) -> list[dict]:
    phase = None
    owner = None
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        header = _header(line)
        if header:
            phase, owner = header
            continue
        if phase is None:
            phase = "command"
        rows.append(
            {
                "phase": phase,
                "timing": "during",
                "text": line[:4000],
                "owner_label": owner or "Geral",
            }
        )
    return rows


def _header(line: str) -> tuple[str, str | None] | None:
    if len(line) > 80 or line.endswith("."):
        return None
    match = re.match(r"^(.*?)(?:\(([^)]{1,80})\))?\s*$", line)
    if not match:
        return None
    label = match.group(1).strip()
    for name, pattern in _PHASES:
        if pattern.search(label) and len(label) <= 40:
            return name, (match.group(2).strip() if match.group(2) else None)
    return None


def commit_rows(db: Session, version_id: int, rows: list[dict]) -> dict:
    version = version_or_404(db, version_id)
    created = 0
    for row in rows:
        ability = _ability(db, version.list_id, row)
        text = row["text"][:4000]
        phase = row["phase"]
        existing = db.scalar(
            select(RuleEffect).where(
                RuleEffect.ability_id == ability.id,
                RuleEffect.phase == phase,
                RuleEffect.effect_text == text,
            )
        )
        if existing:
            continue
        upsert_effect(
            db,
            ability.id,
            {
                "phase": phase,
                "timing": row.get("timing") or "during",
                "effect_kind": row.get("effect_kind") or "reminder",
                "restriction_key": row.get("restriction_key"),
                "condition_json": row.get("condition_json") or {},
                "owner_label": (row.get("owner_label") or row.get("owner", {}).get("name") or "Geral")[:200],
                "effect_text": text,
                "is_hypothesis": bool(row.get("is_hypothesis")),
            },
        )
        created += 1
    return {"version_id": version.id, "created": created}


def _ability(db: Session, list_id: int, row: dict) -> Ability:
    owner = row.get("owner") or {"kind": "general", "name": row.get("owner_label") or "Geral"}
    kind = owner.get("kind") or "general"
    name = (owner.get("name") or row.get("owner_label") or "Geral")[:200]
    faction_id = datasheet_id = detachment_id = None
    if kind == "unit":
        datasheet_id = owner.get("datasheet_id")
        if not datasheet_id:
            err(400, "invalid_input", "Unidade sem datasheet")
    elif kind == "detachment":
        detachment_id = owner.get("detachment_id")
        if not detachment_id:
            err(400, "invalid_input", "Detachment sem id")
        kind = "detachment"
    else:
        kind = "general"
    found = db.scalar(
        select(Ability).where(
            Ability.kind == kind,
            Ability.name == name,
            Ability.faction_id.is_(None) if faction_id is None else Ability.faction_id == faction_id,
            Ability.datasheet_id.is_(None) if datasheet_id is None else Ability.datasheet_id == datasheet_id,
            Ability.detachment_id.is_(None) if detachment_id is None else Ability.detachment_id == detachment_id,
        )
    )
    if found:
        return found
    row_ability = Ability(
        kind=kind,
        faction_id=faction_id,
        datasheet_id=datasheet_id,
        detachment_id=detachment_id,
        name=name,
        summary_user=row.get("text", "")[:4000],
        is_hypothesis=bool(row.get("is_hypothesis")),
    )
    db.add(row_ability)
    db.flush()
    return row_ability
