import json
from pathlib import Path

from app.services.condition import FACT_KEYS, guide_match

ROOT = Path(__file__).resolve().parents[2]


def test_guide_json_matches_client_contract():
    rows = json.loads((ROOT / "fixtures" / "conditions" / "guide.json").read_text(encoding="utf-8-sig"))
    for row in rows:
        include, conditional = guide_match(row["node"], row["facts"])
        assert (include, conditional) == (row["expected"]["include"], row["expected"]["conditional"]), row["name"]


def test_fact_keys_have_a_guide_case():
    blob = (ROOT / "fixtures" / "conditions" / "guide.json").read_text(encoding="utf-8")
    for key in FACT_KEYS:
        assert key in blob, key
