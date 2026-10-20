from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

InputFormat = Literal[
    "nr_json",
    "nr_text_simple",
    "nr_text_wtc_compact",
    "nr_text_wtc_full",
    "nr_text_unknown",
]
FORMATS = {
    "nr_json",
    "nr_text_simple",
    "nr_text_wtc_compact",
    "nr_text_wtc_full",
    "nr_text_unknown",
}


class WeaponStats(BaseModel):
    kind: Literal["ranged", "melee", "wargear", "unknown"] = "unknown"
    range_in: int | None = None
    attacks: str | None = None
    skill: int | None = None
    strength: int | None = None
    ap: int | None = None
    damage: str | None = None
    keywords: list[str] = Field(default_factory=list)


class ParsedWargear(BaseModel):
    name: str
    count: int = 1
    stats: WeaponStats | None = None


class ParsedModel(BaseModel):
    name: str
    count: int
    wargear: list[ParsedWargear] = Field(default_factory=list)


class LeadingRef(BaseModel):
    name: str = ""
    index: int | None = None
    target_id: str | None = None


class ParsedUnit(BaseModel):
    line_no: int | None = None
    json_path: str | None = None
    export_ref: str | None = None
    nr_id: str | None = None
    name: str
    model_count: int = 1
    points: int = 0
    wargear: list[ParsedWargear] = Field(default_factory=list)
    models: list[ParsedModel] = Field(default_factory=list)
    enhancement_name: str | None = None
    enhancement_points: int | None = None
    is_warlord: bool = False
    is_character: bool = False
    keywords: list[str] = Field(default_factory=list)
    leading: list[LeadingRef] = Field(default_factory=list)
    attached_to: str | None = None
    movement: int | None = None
    toughness: int | None = None
    save: int | None = None
    invuln: int | None = None
    wounds: int | None = None
    leadership: int | None = None
    oc: int | None = None
    fnp: int | None = None
    base_size_mm: str | None = None
    ability_names: list[str] = Field(default_factory=list)


class DetachmentHeader(BaseModel):
    name: str
    variant: str | None = None


class EnhancementHeader(BaseModel):
    name: str
    points: int | None = None
    export_ref: str | None = None
    unit_name: str | None = None


class Header(BaseModel):
    faction_name: str | None = None
    detachments: list[DetachmentHeader] = Field(default_factory=list)
    force_disposition: str | None = None
    battle_size: str | None = None
    points_limit: int | None = None
    list_name: str | None = None
    total_points_declared: int | None = None
    warlord_ref: str | None = None
    warlord_name: str | None = None
    enhancements: list[EnhancementHeader] = Field(default_factory=list)
    number_of_units: int | None = None
    secondaries: list[str] = Field(default_factory=list)
    points_include_enhancement: bool | None = None
    points_sum: int = 0


class LeaderPair(BaseModel):
    leader_line: int | None = None
    leader_path: str | None = None
    bodyguard_line: int | None = None
    bodyguard_path: str | None = None
    leader_name: str
    bodyguard_name: str
    source: str = "import"


class Ambiguity(BaseModel):
    leader_line: int | None = None
    leader_path: str | None = None
    leader_name: str
    bodyguard_name: str
    index: int | None = None
    reason: str


class ParseWarning(BaseModel):
    line_no: int | None = None
    json_path: str | None = None
    text: str = ""
    reason: str
    detail: str | None = None


class ParseResult(BaseModel):
    format: InputFormat = "nr_text_unknown"
    parser_version: str = "1"
    parse_hash: str = ""
    generator: str | None = None
    header: Header = Field(default_factory=Header)
    units: list[ParsedUnit] = Field(default_factory=list)
    leader_pairs: list[LeaderPair] = Field(default_factory=list)
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    warnings: list[ParseWarning] = Field(default_factory=list)
