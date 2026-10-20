from app.services.cheatsheet import parse_cheatsheet
from app.services.condition import ConditionError, validate_condition
import pytest


def test_phase_headers_pt_en():
    rows = parse_cheatsheet("Movement (Be'lakor)\nlembrar o flanco\nFim de turno\nprimária")
    assert rows[0]["phase"] == "movement"
    assert rows[0]["owner_label"] == "Be'lakor"
    assert rows[1]["phase"] == "end_of_turn"


def test_condition_limits():
    validate_condition({"all": [{"phase": "shooting"}, {"state.moved": "advanced"}, {"weapon_keyword": "ASSAULT"}]})
    with pytest.raises(ConditionError):
        validate_condition({"nope": 1})
