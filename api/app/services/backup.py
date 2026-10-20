from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import Numeric, select, text
from sqlalchemy.orm import Session

from app.models import (
    Ability,
    ArmyList,
    Attachment,
    BsdataImport,
    CpLedger,
    Datasheet,
    Detachment,
    Enhancement,
    Faction,
    FactionRoundState,
    Game,
    GameEvent,
    GameScore,
    GameTurn,
    ImportRow,
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
)

ORDER = [
    Faction,
    BsdataImport,
    Detachment,
    Datasheet,
    Weapon,
    Ability,
    Enhancement,
    RuleEffect,
    TargetProfile,
    ArmyList,
    ImportRow,
    ListVersion,
    ListVersionDetachment,
    ListUnit,
    ListUnitModel,
    ListUnitWargear,
    Attachment,
    WeaponCheckMark,
    Mission,
    Game,
    GameEvent,
    GameTurn,
    UnitState,
    StratagemUse,
    CpLedger,
    ObjectiveControl,
    GameScore,
    FactionRoundState,
    MapBoard,
    MapPlacement,
]
SERIAL = [
    "bsdata_imports",
    "factions",
    "detachments",
    "datasheets",
    "weapons",
    "abilities",
    "enhancements",
    "rule_effects",
    "target_profiles",
    "lists",
    "imports",
    "list_versions",
    "list_units",
    "list_unit_models",
    "list_unit_wargear",
    "attachments",
    "missions",
    "maps",
    "map_placements",
]


def export_backup(db: Session) -> dict:
    tables = {}
    for model in ORDER:
        tables[model.__tablename__] = [_export_row(model, item) for item in db.scalars(select(model)).all()]
    return {"backup_version": 1, "tables": tables}


def restore_backup(db: Session, payload: dict, snapshot_dir: Path) -> None:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    (snapshot_dir / f"pre-restore-{stamp}.json").write_text(
        json.dumps(export_backup(db), ensure_ascii=False),
        encoding="utf-8",
    )
    db.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    names = ", ".join(model.__tablename__ for model in reversed(ORDER))
    db.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    tables = payload.get("tables") or {}
    pointers = {row["id"]: row.get("current_version_id") for row in tables.get("lists", [])}
    for model in ORDER:
        for raw in tables.get(model.__tablename__, []):
            values = _coerce(model, raw)
            if model is ArmyList:
                values["current_version_id"] = None
            db.execute(model.__table__.insert().values(**values))
    for list_id, version_id in pointers.items():
        if version_id:
            db.execute(
                text("UPDATE lists SET current_version_id = :version WHERE id = :id"),
                {"version": version_id, "id": list_id},
            )
    for table in SERIAL:
        db.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 1), 1))"
            )
        )


def _export_row(model, item) -> dict:
    data = {}
    for col in model.__table__.columns:
        value = getattr(item, col.key)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, UUID):
            value = str(value)
        elif isinstance(value, Decimal):
            value = str(value)
        data[col.key] = value
    return data


def _coerce(model, raw: dict) -> dict:
    values = {}
    for col in model.__table__.columns:
        value = raw.get(col.key)
        type_name = type(col.type).__name__
        if isinstance(value, str) and type_name.startswith("DateTime"):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        elif isinstance(value, str) and "UUID" in type_name:
            value = UUID(value)
        elif isinstance(value, str) and isinstance(col.type, Numeric):
            value = Decimal(value)
        values[col.key] = value
    return values
