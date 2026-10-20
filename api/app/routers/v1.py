from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import db_session
from app.errors import err
from app.models import (
    Ability,
    ArmyList,
    BsdataImport,
    Datasheet,
    Detachment,
    Enhancement,
    Faction,
    Game,
    GameEvent,
    ListUnit,
    ListVersion,
    StratagemUse,
    UnitState,
    MapBoard,
    MapPlacement,
    Mission,
    TargetProfile,
    Weapon,
    WeaponCheckMark,
)
from app.security import COOKIE, allow, login, logout, require_session
from app.services.backup import export_backup, restore_backup
from app.services.bsdata import fetch as bsdata_fetch
from app.services.bsdata import sync as bsdata_sync
from app.services.bsdata.parse import parse_faction
from app.services.cheatsheet import commit_rows, parse_cheatsheet
from app.services.resolve import commit_import, preview
from app.services.views import (
    build_bundle,
    bundle_etag,
    consolidated,
    diff_versions,
    game_detail,
    guide_markdown,
    map_dict,
    replace_attachments,
    sync_events,
    turn_guide,
    units_for,
    upsert_effect,
    version_or_404,
)

router = APIRouter(prefix="/api/v1")


def _backup_dir() -> Path:
    return Path(get_settings().backup_dir)


def db() -> Session:
    return Depends(db_session)  # type: ignore[return-value]


def authed(request: Request, database: Session = Depends(db_session)):
    return require_session(request, database)


def _dump(row) -> dict:
    data = {}
    for col in row.__table__.columns:
        value = getattr(row, col.key)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, uuid.UUID):
            value = str(value)
        elif isinstance(value, Decimal):
            value = float(value)
        data[col.key] = value
    return data


def _confirm(body: dict, word: str) -> None:
    if body.get("confirm") != word:
        err(409, "confirm_required", f"Confirme com {word}")


def _disposition(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:80] or "download"
    from urllib.parse import quote

    return f"attachment; filename=\"{cleaned}\"; filename*=UTF-8''{quote(name)}"


class TokenIn(BaseModel):
    token: str = Field(min_length=8, max_length=500)


class ParseIn(BaseModel):
    raw_text: str
    format_hint: str | None = None


class ImportIn(BaseModel):
    raw_text: str
    target: dict
    resolutions: dict = Field(default_factory=dict)
    parse_hash: str


class GameIn(BaseModel):
    id: uuid.UUID
    list_version_id: int
    bundle_etag: str
    first_player: str
    opponent_name: str | None = None
    opponent_faction: str | None = None
    mission_name: str | None = None
    cp_me: int = 0
    cp_opponent: int = 0


class SyncIn(BaseModel):
    game_id: uuid.UUID
    events: list[dict]


class BsdataIn(BaseModel):
    repo: str = Field(pattern=r"^wh40k-\d{1,2}e$")
    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    catalogue: str = Field(min_length=6, max_length=130)
    faction_id: int | None = None
    apply: bool = False


@router.get("/health")
def health(database: Session = Depends(db_session)):
    return {"status": "ok"}


@router.post("/session")
def open_session(body: TokenIn, request: Request, response: Response, database: Session = Depends(db_session)):
    raw = login(database, body.token, request.headers.get("user-agent"), request.client.host if request.client else "local")
    response.set_cookie(COOKIE, raw, max_age=90 * 24 * 3600, httponly=True, secure=True, samesite="strict", path="/")
    return {"ok": True}


@router.delete("/session")
def close_session(request: Request, response: Response, database: Session = Depends(db_session), _s=Depends(authed)):
    logout(database, request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    return {"ok": True}


@router.get("/backup")
def backup(database: Session = Depends(db_session), _s=Depends(authed)):
    return export_backup(database)


@router.post("/restore")
def restore(body: dict, database: Session = Depends(db_session), _s=Depends(authed)):
    _confirm(body, "RESTAURAR")
    if "data" not in body:
        err(400, "invalid_input", "Backup ausente")
    restore_backup(database, body["data"], _backup_dir())
    return {"ok": True}


@router.post("/imports/parse")
def parse_import(body: ParseIn, request: Request, database: Session = Depends(db_session), _s=Depends(authed)):
    client = request.client.host if request.client else "local"
    if not allow(f"parse:{client}", 30, 60):
        err(429, "rate_limited", "Muitos parses")
    result = preview(body.raw_text, body.format_hint)
    return result.model_dump(mode="json")


@router.post("/imports")
def create_import(body: ImportIn, database: Session = Depends(db_session), _s=Depends(authed)):
    return commit_import(database, body.raw_text, body.target, body.resolutions, body.parse_hash)


@router.get("/lists")
def list_lists(database: Session = Depends(db_session), _s=Depends(authed)):
    rows = []
    for item in database.scalars(select(ArmyList).order_by(ArmyList.id)).all():
        payload = _dump(item)
        version = database.get(ListVersion, item.current_version_id) if item.current_version_id else None
        payload["current_version"] = _dump(version) if version else None
        rows.append(payload)
    return rows


@router.get("/lists/{list_id}")
def get_list(list_id: int, database: Session = Depends(db_session), _s=Depends(authed)):
    item = database.get(ArmyList, list_id)
    if item is None:
        err(404, "not_found", "Lista não encontrada")
    payload = _dump(item)
    version = database.get(ListVersion, item.current_version_id) if item.current_version_id else None
    payload["current_version"] = consolidated(database, version) if version else None
    return payload


@router.patch("/lists/{list_id}")
def patch_list(list_id: int, body: dict, database: Session = Depends(db_session), _s=Depends(authed)):
    item = database.get(ArmyList, list_id)
    if item is None:
        err(404, "not_found", "Lista não encontrada")
    if "name" in body:
        item.name = str(body["name"])[:200]
    if "archived" in body:
        item.archived = bool(body["archived"])
    return _dump(item)


def _detach_finished_games(database: Session, version_ids: list[int], linked: list[Game], list_name: str) -> None:
    """Partida finalizada fica no histórico. As linhas da mesa apontam para as unidades e seguram a lista."""
    game_ids = [game.id for game in linked]
    if game_ids:
        database.execute(delete(UnitState).where(UnitState.game_id.in_(game_ids)))
    if version_ids:
        unit_ids = list(database.scalars(select(ListUnit.id).where(ListUnit.list_version_id.in_(version_ids))).all())
        if unit_ids:
            database.execute(
                update(StratagemUse)
                .where(StratagemUse.target_list_unit_id.in_(unit_ids))
                .values(target_list_unit_id=None)
            )
    for game in linked:
        if not game.list_label:
            game.list_label = list_name
        game.list_version_id = None
    database.flush()


@router.delete("/lists/{list_id}")
def delete_list(list_id: int, body: dict, database: Session = Depends(db_session), _s=Depends(authed)):
    _confirm(body, "EXCLUIR")
    item = database.get(ArmyList, list_id)
    if item is None:
        err(404, "not_found", "Lista não encontrada")
    version_ids = list(database.scalars(select(ListVersion.id).where(ListVersion.list_id == item.id)).all())
    linked = database.scalars(select(Game).where(Game.list_version_id.in_(version_ids or [0]))).all()
    if any(game.status == "active" for game in linked):
        err(409, "list_in_use", "Partida em andamento. Finalize ou apague a partida antes.")
    _detach_finished_games(database, version_ids, linked, item.name)
    var_objBackup = _backup_dir()
    var_objBackup.mkdir(parents=True, exist_ok=True)
    (var_objBackup / f"list-{list_id}.json").write_text(
        __import__("json").dumps(export_backup(database), ensure_ascii=False), encoding="utf-8"
    )
    database.delete(item)
    try:
        database.flush()
    except IntegrityError:
        database.rollback()
        err(409, "list_in_use", "Essa lista tem partida ou mapa gravado. Apague isso antes da lista.")
    return {"ok": True}


@router.get("/lists/{list_id}/versions")
def list_versions(list_id: int, database: Session = Depends(db_session), _s=Depends(authed)):
    rows = database.scalars(select(ListVersion).where(ListVersion.list_id == list_id).order_by(ListVersion.version_no)).all()
    return [_dump(row) for row in rows]


@router.get("/versions/{vid}")
def get_version(vid: int, database: Session = Depends(db_session), _s=Depends(authed)):
    return consolidated(database, version_or_404(database, vid))


@router.patch("/versions/{vid}")
def patch_version(vid: int, body: dict, database: Session = Depends(db_session), _s=Depends(authed)):
    extra = set(body) - {"label"}
    if extra:
        err(409, "version_immutable", "Versão imutável", errors=sorted(extra))
    version = version_or_404(database, vid)
    if "label" in body:
        version.label = body["label"]
    return _dump(version)


@router.get("/versions/{vid}/attachments")
def get_attachments(vid: int, database: Session = Depends(db_session), _s=Depends(authed)):
    return consolidated(database, version_or_404(database, vid))["attachments"]


@router.put("/versions/{vid}/attachments")
def put_attachments(vid: int, body: dict, database: Session = Depends(db_session), _s=Depends(authed)):
    version = version_or_404(database, vid)
    return replace_attachments(database, version, body.get("pairs") or [])


@router.get("/versions/{left}/diff/{right}")
def diff(left: int, right: int, database: Session = Depends(db_session), _s=Depends(authed)):
    return diff_versions(database, left, right)


@router.get("/versions/{vid}/turn-guide")
def guide(vid: int, phase: str | None = None, turn_owner: str | None = None, unit_id: int | None = None, database: Session = Depends(db_session), _s=Depends(authed)):
    return turn_guide(database, version_or_404(database, vid), phase, turn_owner, unit_id)


@router.get("/versions/{vid}/turn-guide/export.md")
def guide_md(vid: int, database: Session = Depends(db_session), _s=Depends(authed)):
    version = version_or_404(database, vid)
    text = guide_markdown(turn_guide(database, version, None, None, None))
    return PlainTextResponse(text, media_type="text/markdown", headers={"Content-Disposition": _disposition(f"turn-guide-{vid}.md")})


@router.get("/versions/{vid}/bundle")
def bundle(vid: int, request: Request, database: Session = Depends(db_session), _s=Depends(authed)):
    payload = build_bundle(database, version_or_404(database, vid))
    tag = bundle_etag(payload)
    headers = {"ETag": tag, "Cache-Control": "private, no-cache", "Vary": "Cookie"}
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(payload, headers=headers)


@router.post("/cheatsheet/parse")
def cheatsheet_parse(body: dict, _s=Depends(authed)):
    return {"rows": parse_cheatsheet(body.get("text") or "")}


@router.post("/cheatsheet/commit")
def cheatsheet_commit(body: dict, database: Session = Depends(db_session), _s=Depends(authed)):
    return commit_rows(database, int(body["version_id"]), body.get("rows") or [])


@router.post("/games")
def create_game(body: GameIn, database: Session = Depends(db_session), _s=Depends(authed)):
    if body.first_player not in {"me", "opponent"}:
        err(400, "invalid_input", "first_player inválido")
    existing = database.get(Game, body.id)
    if existing:
        return game_detail(database, existing)
    if database.get(ListVersion, body.list_version_id) is None:
        err(404, "not_found", "Versão não encontrada")
    game = Game(
        id=body.id,
        list_version_id=body.list_version_id,
        bundle_etag=body.bundle_etag,
        first_player=body.first_player,
        opponent_name=body.opponent_name,
        opponent_faction=body.opponent_faction,
        mission_name=body.mission_name,
        current_player=body.first_player,
        cp_me=max(0, min(99, body.cp_me)),
        cp_opponent=max(0, min(99, body.cp_opponent)),
    )
    database.add(game)
    database.flush()
    return game_detail(database, game)


@router.get("/games")
def list_games(status: str | None = None, database: Session = Depends(db_session), _s=Depends(authed)):
    query = select(Game).order_by(Game.created_at.desc())
    if status:
        query = query.where(Game.status == status)
    return [game_detail(database, game) for game in database.scalars(query).all()]


@router.get("/games/{game_id}")
def get_game(game_id: uuid.UUID, database: Session = Depends(db_session), _s=Depends(authed)):
    game = database.get(Game, game_id)
    if game is None:
        err(404, "not_found", "Partida não encontrada")
    return game_detail(database, game)


@router.post("/games/sync")
def games_sync(body: SyncIn, database: Session = Depends(db_session), _s=Depends(authed)):
    if len(body.events) > 500:
        err(400, "invalid_input", "No máximo 500 eventos")
    return sync_events(database, body.game_id, body.events)


@router.get("/games/{game_id}/events")
def game_events(game_id: uuid.UUID, after_seq: int = 0, database: Session = Depends(db_session), _s=Depends(authed)):
    rows = database.scalars(
        select(GameEvent).where(GameEvent.game_id == game_id, GameEvent.seq > after_seq).order_by(GameEvent.seq)
    ).all()
    return [
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


@router.patch("/games/{game_id}")
def patch_game(game_id: uuid.UUID, body: dict, database: Session = Depends(db_session), _s=Depends(authed)):
    game = database.get(Game, game_id)
    if game is None:
        err(404, "not_found", "Partida não encontrada")
    if "status" in body:
        if body["status"] not in {"active", "finished", "abandoned"}:
            err(400, "invalid_input", "Status inválido")
        game.status = body["status"]
    if "result" in body:
        if body["result"] not in {"win", "loss", "draw", None}:
            err(400, "invalid_input", "Resultado inválido")
        game.result = body["result"]
    if body.get("list_label"):
        game.list_label = str(body["list_label"])[:200]
    return game_detail(database, game)


@router.delete("/games/{game_id}")
def delete_game(game_id: uuid.UUID, body: dict, database: Session = Depends(db_session), _s=Depends(authed)):
    _confirm(body, "EXCLUIR")
    game = database.get(Game, game_id)
    if game is None:
        err(404, "not_found", "Partida não encontrada")
    database.delete(game)
    return {"ok": True}


@router.put("/list-units/{unit_id}/weapon-check")
def mark_weapon(unit_id: int, body: dict, database: Session = Depends(db_session), _s=Depends(authed)):
    unit = database.get(ListUnit, unit_id)
    if unit is None:
        err(404, "not_found", "Unidade não encontrada")
    row = database.get(WeaponCheckMark, unit_id)
    if row is None:
        row = WeaponCheckMark(list_unit_id=unit_id)
        database.add(row)
    row.chosen_loadout_label = body.get("chosen_loadout_label")
    database.flush()
    return _dump(row)


@router.delete("/list-units/{unit_id}/weapon-check")
def unmark_weapon(unit_id: int, database: Session = Depends(db_session), _s=Depends(authed)):
    row = database.get(WeaponCheckMark, unit_id)
    if row:
        database.delete(row)
    return {"ok": True}


def _crud(model, path: str, writable: set[str]):
    @router.get(path, name=f"list_{path}")
    def _list(database: Session = Depends(db_session), _s=Depends(authed)):
        return [_dump(row) for row in database.scalars(select(model).order_by(model.id).limit(5000)).all()]

    @router.post(path)
    def _create(body: dict, database: Session = Depends(db_session), _s=Depends(authed)):
        row = model()
        _assign(row, body, writable)
        database.add(row)
        database.flush()
        return _dump(row)

    @router.patch(path + "/{item_id}")
    def _patch(item_id: int, body: dict, database: Session = Depends(db_session), _s=Depends(authed)):
        row = database.get(model, item_id)
        if row is None:
            err(404, "not_found", "Não encontrado")
        _assign(row, body, writable)
        return _dump(row)

    @router.delete(path + "/{item_id}")
    def _delete(item_id: int, database: Session = Depends(db_session), _s=Depends(authed)):
        row = database.get(model, item_id)
        if row is None:
            err(404, "not_found", "Não encontrado")
        database.delete(row)
        return {"ok": True}


def _assign(row, body: dict, writable: set[str]) -> None:
    for key, value in body.items():
        if key not in writable:
            continue
        if key == "accent_color" and not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(value)):
            err(422, "validation_error", "Cor inválida")
        if key == "keywords" and isinstance(value, list) and len(value) > 50:
            err(422, "validation_error", "Keywords demais")
        if key == "condition_json":
            from app.services.condition import ConditionError, validate_condition

            try:
                validate_condition(value or {})
            except ConditionError as exc:
                err(422, "validation_error", str(exc))
        setattr(row, key, value)


_crud(Faction, "/factions", {"name", "short_name", "accent_color", "source", "source_ref"})
_crud(Detachment, "/detachments", {"faction_id", "name", "variant", "notes"})
_crud(Datasheet, "/datasheets", {"faction_id", "name", "movement", "toughness", "save", "invuln", "wounds", "leadership", "oc", "fnp", "keywords", "base_size_mm", "is_character", "allows_two_leaders", "is_stub", "source"})
_crud(Weapon, "/weapons", {"datasheet_id", "name", "kind", "range_in", "attacks", "skill", "strength", "ap", "damage", "keywords", "is_stub"})
_crud(Ability, "/abilities", {"kind", "faction_id", "datasheet_id", "detachment_id", "name", "cp_cost", "use_limit", "usable_turn", "summary_user", "is_hypothesis"})
_crud(Enhancement, "/enhancements", {"detachment_id", "name", "points", "restrictions", "ability_id"})
_crud(TargetProfile, "/target-profiles", {"name", "toughness", "save", "invuln", "wounds", "fnp", "models", "keywords"})
_crud(Mission, "/missions", {"name", "deployment_type", "board_w_in", "board_h_in", "zones_json", "objectives_json", "primary_summary"})


@router.get("/abilities/{ability_id}/effects")
def list_effects(ability_id: int, database: Session = Depends(db_session), _s=Depends(authed)):
    from app.models import RuleEffect

    rows = database.scalars(select(RuleEffect).where(RuleEffect.ability_id == ability_id)).all()
    return [_dump(row) for row in rows]


@router.post("/abilities/{ability_id}/effects")
def create_effect(ability_id: int, body: dict, database: Session = Depends(db_session), _s=Depends(authed)):
    if database.get(Ability, ability_id) is None:
        err(404, "not_found", "Ability não encontrada")
    return _dump(upsert_effect(database, ability_id, body))


@router.get("/effects")
def all_effects(database: Session = Depends(db_session), _s=Depends(authed)):
    from app.models import RuleEffect

    rows = database.scalars(select(RuleEffect).order_by(RuleEffect.ability_id, RuleEffect.sort_order).limit(5000)).all()
    return [_dump(row) for row in rows]


@router.delete("/effects/{effect_id}")
def delete_effect(effect_id: int, database: Session = Depends(db_session), _s=Depends(authed)):
    from app.models import RuleEffect

    row = database.get(RuleEffect, effect_id)
    if row is None:
        err(404, "not_found", "Efeito não encontrado")
    database.delete(row)
    return {"ok": True}


@router.get("/bsdata/repos/{repo}/catalogues")
def bsdata_catalogues(repo: str, _s=Depends(authed)):
    return bsdata_fetch.latest(repo)


@router.post("/bsdata/import")
def bsdata_import(body: BsdataIn, database: Session = Depends(db_session), _s=Depends(authed)):
    files = bsdata_fetch.tree(body.repo, body.sha)
    chosen = next((item for item in files if item["name"] == body.catalogue), None)
    if chosen is None or chosen["library"] or chosen["system"]:
        err(422, "validation_error", "Escolha um catálogo jogável")
    loader = bsdata_fetch.Loader(body.repo, body.sha, files)
    parsed = parse_faction(loader.load_with_links(body.catalogue), body.catalogue, f"{body.repo}@{body.sha[:12]}")
    return bsdata_sync.sync(database, parsed, body.repo, body.sha, body.faction_id, body.apply)


@router.get("/bsdata/imports")
def bsdata_imports(database: Session = Depends(db_session), _s=Depends(authed)):
    rows = database.scalars(select(BsdataImport).order_by(BsdataImport.imported_at.desc()).limit(50)).all()
    return [_dump(row) for row in rows]


@router.get("/maps")
def list_maps(database: Session = Depends(db_session), _s=Depends(authed)):
    return [_dump(row) for row in database.scalars(select(MapBoard)).all()]


@router.post("/maps")
def create_map(body: dict, database: Session = Depends(db_session), _s=Depends(authed)):
    board = MapBoard(
        list_version_id=body["list_version_id"],
        mission_id=body.get("mission_id"),
        name=body.get("name") or "Mapa",
        side=body.get("side"),
        terrain_json=body.get("terrain_json") or [],
        notes=body.get("notes"),
    )
    database.add(board)
    database.flush()
    return _dump(board)


@router.get("/maps/{map_id}")
def get_map(map_id: int, database: Session = Depends(db_session), _s=Depends(authed)):
    board = database.get(MapBoard, map_id)
    if board is None:
        err(404, "not_found", "Mapa não encontrado")
    units = {unit.id: unit for unit in units_for(database, board.list_version_id)}
    placements = database.scalars(select(MapPlacement).where(MapPlacement.map_id == map_id)).all()
    return map_dict(board, list(placements), units)


@router.put("/maps/{map_id}/placements")
def put_placements(map_id: int, body: dict, database: Session = Depends(db_session), _s=Depends(authed)):
    board = database.get(MapBoard, map_id)
    if board is None:
        err(404, "not_found", "Mapa não encontrado")
    database.query(MapPlacement).filter(MapPlacement.map_id == map_id).delete()
    for item in body.get("placements") or []:
        database.add(
            MapPlacement(
                map_id=map_id,
                list_version_id=board.list_version_id,
                list_unit_id=item["list_unit_id"],
                x_in=item.get("x_in"),
                y_in=item.get("y_in"),
                rotation_deg=item.get("rotation_deg") or 0,
                state=item.get("state") or "on_table",
                first_target=item.get("first_target"),
            )
        )
    database.flush()
    return get_map(map_id, database)


@router.get("/maps/{map_id}/export.html")
def export_map(map_id: int, database: Session = Depends(db_session), _s=Depends(authed)):
    from app.services.views import render_map_html

    payload = get_map(map_id, database)
    html = render_map_html(payload["name"], payload["placements"])
    return Response(
        content=html,
        media_type="text/html",
        headers={
            "Content-Disposition": _disposition(f"{payload['name']}.html"),
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )
