from __future__ import annotations

import hashlib
import unicodedata

PARSER_VERSION = "1"
MAX_BYTES = 204800


def normalize_input(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    out: list[str] = []
    for ch in text:
        if ch in "\n\t":
            out.append(ch)
            continue
        code = ord(ch)
        if code < 32 or code == 127:
            continue
        out.append(ch)
    return "".join(out)


def compute_hash(normalized: str) -> str:
    blob = f"{PARSER_VERSION}\n".encode() + normalized.encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))
