from __future__ import annotations

import json

from app.services.parse.json_roster import parse_json
from app.services.parse.models import FORMATS, InputFormat, ParseResult, ParseWarning
from app.services.parse.normalize import PARSER_VERSION, compute_hash, normalize_input
from app.services.parse.text_parser import parse_text

__all__ = ["PARSER_VERSION", "parse", "normalize_input", "compute_hash"]


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


def parse(raw: str, format_hint: str | None = None, known_detachments: list[str] | None = None) -> ParseResult:
    """Puro: sem banco. Determinístico para a mesma entrada normalizada."""
    normalized = normalize_input(raw)
    digest = compute_hash(normalized)
    fmt = detect_format(normalized, format_hint)
    if fmt == "nr_json":
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError as exc:
            result = ParseResult(format=fmt, parse_hash=digest, parser_version=PARSER_VERSION)
            result.warnings.append(
                ParseWarning(json_path="$", reason="json_invalid", detail=str(exc)[:200])
            )
            return result
        if not isinstance(payload, dict):
            result = ParseResult(format=fmt, parse_hash=digest, parser_version=PARSER_VERSION)
            result.warnings.append(ParseWarning(json_path="$", reason="json_invalid"))
            return result
        result = parse_json(payload)
    else:
        result = parse_text(normalized, fmt, known_detachments)
    result.format = fmt
    result.parse_hash = digest
    result.parser_version = PARSER_VERSION
    return result
