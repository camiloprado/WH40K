from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _id() -> Mapped[int]:
    return mapped_column(BigInteger, primary_key=True, autoincrement=True)


class Faction(Base):
    __tablename__ = "factions"
    id: Mapped[int] = _id()
    name: Mapped[str] = mapped_column(Text)
    short_name: Mapped[str | None] = mapped_column(Text)
    accent_color: Mapped[str] = mapped_column(Text, default="#8A8A8A")
    source: Mapped[str] = mapped_column(Text, default="user")
    source_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Detachment(Base):
    __tablename__ = "detachments"
    id: Mapped[int] = _id()
    faction_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(Text)
    variant: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="user")
    source_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Datasheet(Base):
    __tablename__ = "datasheets"
    id: Mapped[int] = _id()
    faction_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(Text)
    movement: Mapped[int | None] = mapped_column(SmallInteger)
    toughness: Mapped[int | None] = mapped_column(SmallInteger)
    save: Mapped[int | None] = mapped_column(SmallInteger)
    invuln: Mapped[int | None] = mapped_column(SmallInteger)
    wounds: Mapped[int | None] = mapped_column(SmallInteger)
    leadership: Mapped[int | None] = mapped_column(SmallInteger)
    oc: Mapped[int | None] = mapped_column(SmallInteger)
    fnp: Mapped[int | None] = mapped_column(SmallInteger)
    keywords: Mapped[list] = mapped_column(ARRAY(Text), default=list)
    base_size_mm: Mapped[str | None] = mapped_column(Text)
    is_character: Mapped[bool] = mapped_column(Boolean, default=False)
    allows_two_leaders: Mapped[bool] = mapped_column(Boolean, default=False)
    is_stub: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(Text, default="user")
    source_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Weapon(Base):
    __tablename__ = "weapons"
    id: Mapped[int] = _id()
    datasheet_id: Mapped[int | None] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, default="unknown")
    range_in: Mapped[int | None] = mapped_column(SmallInteger)
    attacks: Mapped[str | None] = mapped_column(Text)
    skill: Mapped[int | None] = mapped_column(SmallInteger)
    strength: Mapped[int | None] = mapped_column(SmallInteger)
    ap: Mapped[int | None] = mapped_column(SmallInteger)
    damage: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list] = mapped_column(ARRAY(Text), default=list)
    is_stub: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(Text, default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Ability(Base):
    __tablename__ = "abilities"
    id: Mapped[int] = _id()
    kind: Mapped[str] = mapped_column(Text)
    faction_id: Mapped[int | None] = mapped_column(BigInteger)
    datasheet_id: Mapped[int | None] = mapped_column(BigInteger)
    detachment_id: Mapped[int | None] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(Text)
    cp_cost: Mapped[int | None] = mapped_column(SmallInteger)
    use_limit: Mapped[str | None] = mapped_column(Text)
    usable_turn: Mapped[str | None] = mapped_column(Text)
    summary_user: Mapped[str | None] = mapped_column(Text)
    is_hypothesis: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(Text, default="user")
    source_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Enhancement(Base):
    __tablename__ = "enhancements"
    id: Mapped[int] = _id()
    detachment_id: Mapped[int | None] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(Text)
    points: Mapped[int | None] = mapped_column(SmallInteger)
    restrictions: Mapped[str | None] = mapped_column(Text)
    ability_id: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(Text, default="user")
    source_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RuleEffect(Base):
    __tablename__ = "rule_effects"
    id: Mapped[int] = _id()
    ability_id: Mapped[int] = mapped_column(BigInteger)
    phase: Mapped[str] = mapped_column(Text)
    turn_owner: Mapped[str] = mapped_column(Text, default="own")
    timing: Mapped[str] = mapped_column(Text, default="during")
    effect_kind: Mapped[str] = mapped_column(Text, default="reminder")
    restriction_key: Mapped[str | None] = mapped_column(Text)
    condition_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    owner_label: Mapped[str] = mapped_column(Text)
    effect_text: Mapped[str] = mapped_column(Text)
    range_in: Mapped[int | None] = mapped_column(SmallInteger)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_hypothesis: Mapped[bool] = mapped_column(Boolean, default=False)
    choice_options: Mapped[list] = mapped_column(JSONB, default=list)
    choice_count: Mapped[int | None] = mapped_column(SmallInteger)
    choice_scope: Mapped[str] = mapped_column(Text, default="turn")
    source: Mapped[str] = mapped_column(Text, default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BsdataImport(Base):
    __tablename__ = "bsdata_imports"
    id: Mapped[int] = _id()
    repo: Mapped[str] = mapped_column(Text)
    sha: Mapped[str] = mapped_column(Text)
    catalogue: Mapped[str] = mapped_column(Text)
    revision: Mapped[int | None] = mapped_column(Integer)
    faction_id: Mapped[int | None] = mapped_column(BigInteger)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TargetProfile(Base):
    __tablename__ = "target_profiles"
    id: Mapped[int] = _id()
    name: Mapped[str] = mapped_column(Text)
    toughness: Mapped[int] = mapped_column(SmallInteger)
    save: Mapped[int] = mapped_column(SmallInteger)
    invuln: Mapped[int | None] = mapped_column(SmallInteger)
    wounds: Mapped[int] = mapped_column(SmallInteger)
    fnp: Mapped[int | None] = mapped_column(SmallInteger)
    models: Mapped[int] = mapped_column(SmallInteger, default=1)
    keywords: Mapped[list] = mapped_column(ARRAY(Text), default=list)
    source_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArmyList(Base):
    __tablename__ = "lists"
    id: Mapped[int] = _id()
    name: Mapped[str] = mapped_column(Text)
    faction_id: Mapped[int | None] = mapped_column(BigInteger)
    current_version_id: Mapped[int | None] = mapped_column(BigInteger)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportRow(Base):
    __tablename__ = "imports"
    id: Mapped[int] = _id()
    list_id: Mapped[int] = mapped_column(BigInteger)
    raw_text: Mapped[str] = mapped_column(Text)
    input_format: Mapped[str] = mapped_column(Text)
    parser_version: Mapped[str] = mapped_column(Text)
    parse_hash: Mapped[str] = mapped_column(Text)
    generator: Mapped[str | None] = mapped_column(Text)
    parsed_json: Mapped[dict] = mapped_column(JSONB)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ListVersion(Base):
    __tablename__ = "list_versions"
    id: Mapped[int] = _id()
    list_id: Mapped[int] = mapped_column(BigInteger)
    version_no: Mapped[int] = mapped_column(Integer)
    import_id: Mapped[int | None] = mapped_column(BigInteger)
    label: Mapped[str | None] = mapped_column(Text)
    faction_name: Mapped[str] = mapped_column(Text)
    detachment_names: Mapped[list] = mapped_column(ARRAY(Text), default=list)
    force_disposition: Mapped[str | None] = mapped_column(Text)
    battle_size: Mapped[str | None] = mapped_column(Text)
    points_limit: Mapped[int | None] = mapped_column(Integer)
    secondaries: Mapped[list] = mapped_column(ARRAY(Text), default=list)
    total_points_declared: Mapped[int | None] = mapped_column(Integer)
    points_include_enhancement: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ListVersionDetachment(Base):
    __tablename__ = "list_version_detachments"
    list_version_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    detachment_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class ListUnit(Base):
    __tablename__ = "list_units"
    id: Mapped[int] = _id()
    list_version_id: Mapped[int] = mapped_column(BigInteger)
    datasheet_name: Mapped[str] = mapped_column(Text)
    datasheet_id: Mapped[int] = mapped_column(BigInteger)
    export_ref: Mapped[str | None] = mapped_column(Text)
    model_count: Mapped[int] = mapped_column(SmallInteger)
    points: Mapped[int] = mapped_column(Integer)
    enhancement_name: Mapped[str | None] = mapped_column(Text)
    enhancement_points: Mapped[int | None] = mapped_column(SmallInteger)
    enhancement_id: Mapped[int | None] = mapped_column(BigInteger)
    is_warlord: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ListUnitModel(Base):
    __tablename__ = "list_unit_models"
    id: Mapped[int] = _id()
    list_unit_id: Mapped[int] = mapped_column(BigInteger)
    model_name: Mapped[str] = mapped_column(Text)
    count: Mapped[int] = mapped_column(SmallInteger)


class ListUnitWargear(Base):
    __tablename__ = "list_unit_wargear"
    id: Mapped[int] = _id()
    list_unit_id: Mapped[int] = mapped_column(BigInteger)
    list_unit_model_id: Mapped[int | None] = mapped_column(BigInteger)
    weapon_name: Mapped[str] = mapped_column(Text)
    weapon_id: Mapped[int | None] = mapped_column(BigInteger)
    count: Mapped[int] = mapped_column(SmallInteger, default=1)


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[int] = _id()
    list_version_id: Mapped[int] = mapped_column(BigInteger)
    leader_list_unit_id: Mapped[int] = mapped_column(BigInteger)
    bodyguard_list_unit_id: Mapped[int] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(Text, default="import")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WeaponCheckMark(Base):
    __tablename__ = "weapon_check_marks"
    list_unit_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    chosen_loadout_label: Mapped[str | None] = mapped_column(Text)


class SessionRow(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = _id()
    token_hash: Mapped[str] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Game(Base):
    __tablename__ = "games"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    list_version_id: Mapped[int | None] = mapped_column(BigInteger)
    list_label: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(Text)
    bundle_etag: Mapped[str] = mapped_column(Text)
    opponent_name: Mapped[str | None] = mapped_column(Text)
    opponent_faction: Mapped[str | None] = mapped_column(Text)
    mission_name: Mapped[str | None] = mapped_column(Text)
    mission_id: Mapped[int | None] = mapped_column(BigInteger)
    first_player: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="active")
    current_round: Mapped[int] = mapped_column(SmallInteger, default=1)
    current_player: Mapped[str] = mapped_column(Text)
    current_phase: Mapped[str] = mapped_column(Text, default="command")
    cp_me: Mapped[int] = mapped_column(SmallInteger, default=0)
    cp_opponent: Mapped[int | None] = mapped_column(SmallInteger)
    vp_me: Mapped[int] = mapped_column(SmallInteger, default=0)
    vp_opponent: Mapped[int] = mapped_column(SmallInteger, default=0)
    last_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GameEvent(Base):
    __tablename__ = "game_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    seq: Mapped[int] = mapped_column(Integer)
    device_id: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    undoes_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GameTurn(Base):
    __tablename__ = "game_turns"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    round: Mapped[int] = mapped_column(SmallInteger)
    player: Mapped[str] = mapped_column(Text)
    phase: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UnitState(Base):
    __tablename__ = "unit_states"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    list_version_id: Mapped[int] = mapped_column(BigInteger)
    list_unit_id: Mapped[int] = mapped_column(BigInteger)
    round: Mapped[int] = mapped_column(SmallInteger)
    player: Mapped[str] = mapped_column(Text)
    moved: Mapped[str] = mapped_column(Text, default="none")
    shot: Mapped[bool] = mapped_column(Boolean, default=False)
    charged: Mapped[bool] = mapped_column(Boolean, default=False)
    fought: Mapped[bool] = mapped_column(Boolean, default=False)
    engaged: Mapped[bool] = mapped_column(Boolean, default=False)
    on_action: Mapped[bool] = mapped_column(Boolean, default=False)
    action_name: Mapped[str | None] = mapped_column(Text)
    battle_shocked: Mapped[bool] = mapped_column(Boolean, default=False)
    below_half: Mapped[bool] = mapped_column(Boolean, default=False)
    destroyed: Mapped[bool] = mapped_column(Boolean, default=False)
    in_reserves: Mapped[bool] = mapped_column(Boolean, default=False)
    lane: Mapped[str] = mapped_column(Text, default="center")
    overrides: Mapped[list] = mapped_column(JSONB, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StratagemUse(Base):
    __tablename__ = "stratagem_uses"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    ability_id: Mapped[int | None] = mapped_column(BigInteger)
    stratagem_name: Mapped[str] = mapped_column(Text)
    round: Mapped[int] = mapped_column(SmallInteger)
    player: Mapped[str] = mapped_column(Text)
    phase: Mapped[str] = mapped_column(Text)
    cp_spent: Mapped[int] = mapped_column(SmallInteger)
    target_list_unit_id: Mapped[int | None] = mapped_column(BigInteger)
    limit_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CpLedger(Base):
    __tablename__ = "cp_ledger"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    round: Mapped[int] = mapped_column(SmallInteger)
    player: Mapped[str] = mapped_column(Text)
    phase: Mapped[str] = mapped_column(Text)
    delta: Mapped[int] = mapped_column(SmallInteger)
    reason: Mapped[str] = mapped_column(Text)
    stratagem_use_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ObjectiveControl(Base):
    __tablename__ = "objective_control"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    round: Mapped[int] = mapped_column(SmallInteger)
    player_turn: Mapped[str] = mapped_column(Text)
    objective_label: Mapped[str] = mapped_column(Text)
    controller: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GameScore(Base):
    __tablename__ = "game_scores"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    round: Mapped[int] = mapped_column(SmallInteger)
    player: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    vp: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FactionRoundState(Base):
    __tablename__ = "faction_round_states"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    round: Mapped[int] = mapped_column(SmallInteger)
    player: Mapped[str] = mapped_column(Text)
    turn_player: Mapped[str | None] = mapped_column(Text)
    phase: Mapped[str | None] = mapped_column(Text)
    state_key: Mapped[str] = mapped_column(Text)
    objectives_controlled: Mapped[int | None] = mapped_column(SmallInteger)
    whole_board: Mapped[bool | None] = mapped_column(Boolean)
    nml_in_shadow: Mapped[bool | None] = mapped_column(Boolean)
    opp_dz_in_shadow: Mapped[bool | None] = mapped_column(Boolean)
    value: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Mission(Base):
    __tablename__ = "missions"
    id: Mapped[int] = _id()
    name: Mapped[str] = mapped_column(Text)
    deployment_type: Mapped[str | None] = mapped_column(Text)
    board_w_in: Mapped[int] = mapped_column(SmallInteger, default=60)
    board_h_in: Mapped[int] = mapped_column(SmallInteger, default=44)
    zones_json: Mapped[list] = mapped_column(JSONB, default=list)
    objectives_json: Mapped[list] = mapped_column(JSONB, default=list)
    primary_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MapBoard(Base):
    __tablename__ = "maps"
    id: Mapped[int] = _id()
    list_version_id: Mapped[int] = mapped_column(BigInteger)
    mission_id: Mapped[int | None] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(Text)
    side: Mapped[str | None] = mapped_column(Text)
    terrain_json: Mapped[list] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MapPlacement(Base):
    __tablename__ = "map_placements"
    id: Mapped[int] = _id()
    map_id: Mapped[int] = mapped_column(BigInteger)
    list_version_id: Mapped[int] = mapped_column(BigInteger)
    list_unit_id: Mapped[int] = mapped_column(BigInteger)
    x_in: Mapped[float | None] = mapped_column(Numeric(5, 2))
    y_in: Mapped[float | None] = mapped_column(Numeric(5, 2))
    rotation_deg: Mapped[float] = mapped_column(Numeric(5, 1), default=0)
    state: Mapped[str] = mapped_column(Text, default="on_table")
    first_target: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
