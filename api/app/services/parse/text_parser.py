from __future__ import annotations

import re

from app.services.parse.leaders import pair_leaders
from app.services.parse.models import (
    DetachmentHeader,
    EnhancementHeader,
    InputFormat,
    ParseResult,
    ParseWarning,
    ParsedModel,
    ParsedUnit,
    ParsedWargear,
    LeadingRef,
)

MAX_LINES = 5000
MAX_LINE = 500

HEADER_RE = re.compile(r"^\+\s*([A-Z][A-Z ]{0,40}):\s*(.{0,450})$")
PLAIN_HEADER_RE = re.compile(
    r"^(FACTION(?: KEYWORD)?|DETACHMENT|FORCE DISPOSITION|TOTAL(?: ARMY POINTS)?|"
    r"WARLORD|ENHANCEMENT|NUMBER OF UNITS|SECONDARY)\s*:\s*(.{0,450})$",
    re.IGNORECASE,
)
PTS_RE = re.compile(r"\((\d{1,6})\s*pts?\)", re.IGNORECASE)
UNIT_HEAD_RE = re.compile(r"^(?:(Char\d{1,3}):\s*)?(\d{1,4})x\s+(.{1,200})$")
ENH_RE = re.compile(r"^Enhancement:\s*(.{1,200}?)\s*\(\+(\d{1,4})\s*pts?\)$", re.IGNORECASE)
LEADING_RE = re.compile(r"^Leading\s+(.{1,200}?)(?:\[(\d{1,3})\])?$", re.IGNORECASE)
MODEL_RE = re.compile(r"^•\s*(\d{1,4})x\s+([^:]{1,200})(?::\s*(.{0,400}))?$")
WITH_RE = re.compile(r"^\s*(\d{1,4})\s+with\s+(.{1,400})$", re.IGNORECASE)
ATTACHED_RE = re.compile(r"^\s*Attached to\s+(.{1,200})$", re.IGNORECASE)
GENERATED_RE = re.compile(r"^Created with\s+(.{1,120})$", re.IGNORECASE)
BULLET_RE = re.compile(r"^(\s*)[●◦∙·]\s*")
ITEM_RE = re.compile(r"^(?:(\d{1,4})x\s+)?([A-Za-z0-9][^,]{0,120})$")
ON_CHAR_RE = re.compile(
    r"^(.{1,200}?)\s*\(on\s+(Char\d{1,3}):\s*(.{1,200})\)\s*(?:\(\+(\d{1,4})\s*pts?\))?$",
    re.IGNORECASE,
)
INT_RE = re.compile(r"(\d{1,6})")


def parse_text(
    text: str,
    fmt: InputFormat,
    known_detachments: list[str] | None = None,
) -> ParseResult:
    result = ParseResult(format=fmt)
    if fmt == "nr_text_unknown":
        result.warnings.append(ParseWarning(reason="unknown_format", text=""))

    raw_lines = text.split("\n")
    if len(raw_lines) > MAX_LINES:
        result.warnings.append(
            ParseWarning(reason="too_many_lines", text=str(len(raw_lines)), line_no=MAX_LINES + 1)
        )
        raw_lines = raw_lines[:MAX_LINES]

    lines = [BULLET_RE.sub(r"\1• ", line) for line in raw_lines]
    state = "TOP"
    current: ParsedUnit | None = None
    current_group: ParsedModel | None = None

    for idx, line in enumerate(lines, start=1):
        if len(line) > MAX_LINE:
            result.warnings.append(
                ParseWarning(line_no=idx, text=line[:80], reason="truncated")
            )
            continue
        stripped = line.strip()
        if not stripped or re.fullmatch(r"\+{5,}", stripped):
            continue
        if re.fullmatch(r"[#=\-]{3,}", stripped) or stripped.startswith("#####"):
            continue
        if stripped.upper() in {
            "CHARACTERS",
            "BATTLELINE",
            "OTHER DATASHEETS",
            "DEDICATED TRANSPORTS",
            "ALLIED UNITS",
        }:
            continue
        if GENERATED_RE.match(stripped):
            result.generator = GENERATED_RE.match(stripped).group(1).strip()  # type: ignore[union-attr]
            continue

        header = HEADER_RE.match(line) or (
            PLAIN_HEADER_RE.match(stripped) if fmt != "nr_text_simple" or line.startswith("+") else None
        )
        if header is None and fmt != "nr_text_simple":
            header = PLAIN_HEADER_RE.match(stripped)
        if header and state == "TOP":
            _apply_header(result, header.group(1), header.group(2), known_detachments)
            continue

        if current is not None and ENH_RE.match(stripped):
            match = ENH_RE.match(stripped)
            assert match
            current.enhancement_name = match.group(1).strip()
            current.enhancement_points = int(match.group(2))
            continue
        if current is not None and LEADING_RE.match(stripped):
            match = LEADING_RE.match(stripped)
            assert match
            index = int(match.group(2)) if match.group(2) else None
            current.leading.append(LeadingRef(name=match.group(1).strip(), index=index))
            continue
        if ATTACHED_RE.match(line) and current is not None:
            match = ATTACHED_RE.match(line)
            assert match
            current.attached_to = match.group(1).strip()
            state = "UNIT"
            current_group = None
            continue
        model = MODEL_RE.match(stripped)
        if model and current is not None:
            wargear, warns = _wargear(model.group(3) or "", idx)
            result.warnings.extend(warns)
            current_group = ParsedModel(name=model.group(2).strip(), count=int(model.group(1)), wargear=wargear)
            current.models.append(current_group)
            state = "MODEL_GROUP"
            continue
        with_line = WITH_RE.match(line)
        if with_line and state == "MODEL_GROUP" and current_group is not None:
            wargear, warns = _wargear(with_line.group(2), idx)
            result.warnings.extend(warns)
            for item in wargear:
                item.count = int(with_line.group(1))
            current_group.wargear.extend(wargear)
            continue

        unit = _parse_unit_line(line, idx, result)
        if unit is not None:
            current = unit
            current_group = None
            state = "UNIT"
            result.units.append(unit)
            continue

        if stripped and not stripped.startswith("+"):
            result.warnings.append(ParseWarning(line_no=idx, text=stripped[:180], reason="unrecognized"))

    _link_header_roles(result)
    _enhancement_sums(result)
    if result.header.faction_name is None:
        result.warnings.append(ParseWarning(reason="faction_missing", text=""))
    if result.header.number_of_units is not None and result.header.number_of_units != len(result.units):
        result.warnings.append(
            ParseWarning(
                reason="unit_count_mismatch",
                text=f"{result.header.number_of_units}!={len(result.units)}",
            )
        )
    pair_leaders(result)
    return result


def _parse_unit_line(line: str, line_no: int, result: ParseResult) -> ParsedUnit | None:
    if line[:1].isspace():
        return None
    matches = list(PTS_RE.finditer(line))
    if not matches:
        return None
    last = matches[-1]
    points = int(last.group(1))
    if points > 10000:
        result.warnings.append(ParseWarning(line_no=line_no, text=line[:180], reason="points_capped"))
        return None
    head = line[: last.start()].rstrip()
    tail = line[last.end() :]
    head_match = UNIT_HEAD_RE.match(head)
    if not head_match:
        return None
    name = head_match.group(3).strip()
    if not name:
        return None
    wargear_text = None
    if tail.startswith(":"):
        wargear_text = tail[1:].strip()[:400]
    wargear, warns = _wargear(wargear_text or "", line_no)
    result.warnings.extend(warns)
    export_ref = head_match.group(1)
    count = int(head_match.group(2))
    return ParsedUnit(
        line_no=line_no,
        export_ref=export_ref,
        name=name,
        model_count=min(count, 200),
        points=points,
        wargear=wargear,
        is_character=bool(export_ref),
    )


def _wargear(text: str, line_no: int) -> tuple[list[ParsedWargear], list[ParseWarning]]:
    if not text.strip():
        return [], []
    items: list[ParsedWargear] = []
    warnings: list[ParseWarning] = []
    for part in text.split(","):
        piece = part.strip()
        if not piece:
            continue
        match = ITEM_RE.match(piece)
        if not match:
            warnings.append(ParseWarning(line_no=line_no, text=piece[:180], reason="wargear_unparsed"))
            continue
        count = int(match.group(1) or "1")
        items.append(ParsedWargear(name=match.group(2).strip(), count=max(1, count)))
    return items, warnings


def _apply_header(
    result: ParseResult,
    key: str,
    value: str,
    known_detachments: list[str] | None,
) -> None:
    norm = re.sub(r"\s+", " ", key).strip().upper()
    value = value.strip()
    if norm in {"FACTION", "FACTION KEYWORD"}:
        result.header.faction_name = value[:200]
    elif norm == "DETACHMENT":
        result.header.detachments.extend(_detachments(value, known_detachments))
    elif norm == "FORCE DISPOSITION":
        result.header.force_disposition = value[:200]
    elif norm.startswith("TOTAL"):
        match = INT_RE.search(value.replace(" ", ""))
        if match:
            result.header.total_points_declared = int(match.group(1))
    elif norm == "WARLORD":
        ref, name = _char_and_name(value)
        result.header.warlord_ref = ref
        result.header.warlord_name = name
    elif norm == "ENHANCEMENT":
        parsed = _enhancement_header(value)
        if parsed:
            result.header.enhancements.append(parsed)
    elif norm == "NUMBER OF UNITS":
        match = INT_RE.search(value)
        if match:
            result.header.number_of_units = int(match.group(1))
    elif norm == "SECONDARY":
        chunks = [c.strip(" -") for c in value.split(" - ") if c.strip(" -")]
        result.header.secondaries.extend(chunks)


def _detachments(value: str, known: list[str] | None) -> list[DetachmentHeader]:
    parts = [value]
    if "," in value and known:
        pieces = [p.strip() for p in value.split(",") if p.strip()]
        known_cf = {k.casefold() for k in known}
        if pieces and all(_detachment_name(p)[0].casefold() in known_cf for p in pieces):
            parts = pieces
    out: list[DetachmentHeader] = []
    for part in parts:
        name, variant = _detachment_name(part)
        if name:
            out.append(DetachmentHeader(name=name[:200], variant=variant[:200] if variant else None))
    return out


def _detachment_name(value: str) -> tuple[str, str | None]:
    match = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", value.strip())
    if not match:
        return value.strip(), None
    return match.group(1).strip(), match.group(2).strip() or None


def _char_and_name(value: str) -> tuple[str | None, str | None]:
    match = re.match(r"^(Char\d{1,3}):\s*(.{1,200})$", value.strip())
    if match:
        return match.group(1), match.group(2).strip()
    return None, value.strip()[:200] or None


def _enhancement_header(value: str) -> EnhancementHeader | None:
    match = ON_CHAR_RE.match(value.strip())
    if match:
        return EnhancementHeader(
            name=match.group(1).strip(),
            export_ref=match.group(2),
            unit_name=match.group(3).strip(),
            points=int(match.group(4)) if match.group(4) else None,
        )
    return EnhancementHeader(name=value[:200])


def _link_header_roles(result: ParseResult) -> None:
    if result.header.warlord_ref or result.header.warlord_name:
        unit = _find_unit(result.units, result.header.warlord_ref, result.header.warlord_name)
        if unit is None:
            result.warnings.append(
                ParseWarning(reason="warlord_missing", text=result.header.warlord_name or "")
            )
        else:
            if (
                result.header.warlord_name
                and unit.name.casefold() != result.header.warlord_name.casefold()
            ):
                result.warnings.append(
                    ParseWarning(
                        line_no=unit.line_no,
                        text=unit.name,
                        reason="warlord_name_divergence",
                        detail="body",
                    )
                )
            unit.is_warlord = True
    for enh in result.header.enhancements:
        unit = _find_unit(result.units, enh.export_ref, enh.unit_name)
        if unit is None:
            continue
        if unit.enhancement_name and enh.name and unit.enhancement_name.casefold() != enh.name.casefold():
            result.warnings.append(
                ParseWarning(
                    line_no=unit.line_no,
                    text=unit.enhancement_name,
                    reason="enhancement_divergence",
                    detail="body",
                )
            )
            continue
        if not unit.enhancement_name:
            unit.enhancement_name = enh.name
            unit.enhancement_points = enh.points


def _find_unit(units: list[ParsedUnit], export_ref: str | None, name: str | None) -> ParsedUnit | None:
    if export_ref:
        for unit in units:
            if unit.export_ref == export_ref:
                return unit
    if name:
        for unit in units:
            if unit.name.casefold() == name.casefold():
                return unit
    return None


def _enhancement_sums(result: ParseResult) -> None:
    declared = result.header.total_points_declared
    unit_sum = sum(unit.points for unit in result.units)
    result.header.points_sum = unit_sum
    positive = [unit.enhancement_points or 0 for unit in result.units if (unit.enhancement_points or 0) > 0]
    if declared is None:
        result.header.points_include_enhancement = None
        return
    if not positive:
        result.header.points_include_enhancement = True
        return
    total_enh = sum(positive)
    if len(positive) == 1:
        if unit_sum == declared:
            result.header.points_include_enhancement = True
        elif unit_sum + positive[0] == declared:
            result.header.points_include_enhancement = False
        else:
            result.header.points_include_enhancement = None
            result.warnings.append(
                ParseWarning(
                    reason="enhancement_sum",
                    text=f"units={unit_sum}; units+enh={unit_sum + positive[0]}; declared={declared}",
                )
            )
        return
    if unit_sum == declared:
        result.header.points_include_enhancement = True
    elif unit_sum + total_enh == declared:
        result.header.points_include_enhancement = False
    else:
        result.header.points_include_enhancement = None
        result.warnings.append(
            ParseWarning(
                reason="enhancement_sum",
                text=f"units={unit_sum}; units+all={unit_sum + total_enh}; declared={declared}",
            )
        )
