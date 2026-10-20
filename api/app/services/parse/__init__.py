from __future__ import annotations

import json

from app.services.parse.json_roster import parse_json
from app.services.parse.models import FORMATS, InputFormat, ParseResult, ParseWarning
from app.services.parse.normalize import PARSER_VERSION, compute_hash, normalize_input
from app.services.parse.text_parser import parse_text

__all__ = ["PARSER_VERSION", "parse", "normalize_input", "compute_hash"]

con_intMaxJsonDepth = 64


def detect_format(text: str, hint: str | None) -> InputFormat:
    stripped = text.lstrip()
    if hint == "nr_json":
        return "nr_json"
    if hint is None and stripped.startswith("{"):
        return "nr_json"
    head = "\n".join(text.splitlines()[:50]).upper()
    if "WTC FULL" in head:
        return "nr_text_wtc_full"
    if "WTC COMPACT" in head:
        return "nr_text_wtc_compact"
    if "+++" in head:
        return "nr_text_simple"
    if hint in FORMATS and hint != "nr_json":
        return hint  # type: ignore[return-value]
    return "nr_text_unknown"


def _json_depth(text: str) -> int:
    var_intDepth = 0
    var_intMax = 0
    var_boolInString = False
    var_boolEscape = False
    for var_strCh in text:
        if var_boolInString:
            if var_boolEscape:
                var_boolEscape = False
            elif var_strCh == "\\":
                var_boolEscape = True
            elif var_strCh == '"':
                var_boolInString = False
            continue
        if var_strCh == '"':
            var_boolInString = True
        elif var_strCh in "{[":
            var_intDepth += 1
            if var_intDepth > var_intMax:
                var_intMax = var_intDepth
        elif var_strCh in "}]":
            var_intDepth = max(0, var_intDepth - 1)
    return var_intMax


def _reject_constant(value: str):
    raise ValueError(f"json_constant:{value}")


def parse(raw: str, format_hint: str | None = None, known_detachments: list[str] | None = None) -> ParseResult:
    """Puro: sem banco. Determinístico para a mesma entrada normalizada."""
    normalized = normalize_input(raw)
    digest = compute_hash(normalized)
    fmt = detect_format(normalized, format_hint)
    if fmt == "nr_json":
        result = ParseResult(format=fmt, parse_hash=digest, parser_version=PARSER_VERSION)
        if _json_depth(normalized) > con_intMaxJsonDepth:
            result.warnings.append(
                ParseWarning(json_path="$", reason="json_invalid", detail="max_depth")
            )
            return result
        try:
            payload = json.loads(normalized, parse_constant=_reject_constant)
        except (json.JSONDecodeError, RecursionError, ValueError) as exc:
            result.warnings.append(
                ParseWarning(json_path="$", reason="json_invalid", detail=str(exc)[:200])
            )
            return result
        if not isinstance(payload, dict):
            result.warnings.append(ParseWarning(json_path="$", reason="json_invalid"))
            return result
        result = parse_json(payload)
    else:
        result = parse_text(normalized, fmt, known_detachments)
    result.format = fmt
    result.parse_hash = digest
    result.parser_version = PARSER_VERSION
    return result
