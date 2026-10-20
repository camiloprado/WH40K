from __future__ import annotations

from app.services.parse.models import Ambiguity, LeaderPair, ParseResult, ParseWarning, ParsedUnit


def _key(unit: ParsedUnit) -> str:
    return unit.name.casefold().strip()


def pair_leaders(result: ParseResult) -> None:
    units = result.units
    by_name: dict[str, list[ParsedUnit]] = {}
    for unit in units:
        by_name.setdefault(_key(unit), []).append(unit)

    used_leaders: set[int] = set()
    used_body: set[int] = set()

    def uid(unit: ParsedUnit) -> int:
        return id(unit)

    by_nr = {unit.nr_id: unit for unit in units if unit.nr_id}
    for leader in units:
        for lead in leader.leading:
            if not lead.target_id or lead.target_id not in by_nr:
                continue
            body = by_nr[lead.target_id]
            if uid(leader) in used_leaders or uid(body) in used_body or leader is body:
                continue
            _add_pair(result, leader, body)
            used_leaders.add(uid(leader))
            used_body.add(uid(body))

    claims: list[tuple[ParsedUnit, str, int | None]] = []
    for unit in units:
        if uid(unit) in used_leaders:
            continue
        for lead in unit.leading:
            if lead.target_id:
                continue
            if lead.name.strip():
                claims.append((unit, lead.name.strip(), lead.index))

    indexed = [c for c in claims if c[2] is not None]
    plain = [c for c in claims if c[2] is None]

    for leader, name, index in indexed:
        candidates = by_name.get(name.casefold(), [])
        if index is None or not (1 <= index <= len(candidates)):
            result.warnings.append(
                ParseWarning(
                    line_no=leader.line_no,
                    json_path=leader.json_path,
                    text=f"Leading {name}[{index}]",
                    reason="leader_index_missing",
                )
            )
            continue
        body = candidates[index - 1]
        if uid(leader) in used_leaders or uid(body) in used_body or leader is body:
            result.ambiguities.append(
                Ambiguity(
                    leader_line=leader.line_no,
                    leader_path=leader.json_path,
                    leader_name=leader.name,
                    bodyguard_name=name,
                    index=index,
                    reason="leader_ambiguous",
                )
            )
            continue
        _add_pair(result, leader, body)
        used_leaders.add(uid(leader))
        used_body.add(uid(body))

    for leader, name, _index in plain:
        if uid(leader) in used_leaders:
            continue
        candidates = [u for u in by_name.get(name.casefold(), []) if uid(u) not in used_body and u is not leader]
        if len(candidates) == 1:
            body = candidates[0]
            _add_pair(result, leader, body)
            used_leaders.add(uid(leader))
            used_body.add(uid(body))
        elif len(candidates) == 0:
            result.warnings.append(
                ParseWarning(
                    line_no=leader.line_no,
                    json_path=leader.json_path,
                    text=name,
                    reason="leader_one_side",
                )
            )
        else:
            result.ambiguities.append(
                Ambiguity(
                    leader_line=leader.line_no,
                    leader_path=leader.json_path,
                    leader_name=leader.name,
                    bodyguard_name=name,
                    reason="leader_ambiguous",
                )
            )

    for body in units:
        if not body.attached_to or uid(body) in used_body:
            continue
        name = body.attached_to.strip()
        candidates = [u for u in by_name.get(name.casefold(), []) if uid(u) not in used_leaders and u is not body]
        if len(candidates) == 1:
            leader = candidates[0]
            _add_pair(result, leader, body)
            used_leaders.add(uid(leader))
            used_body.add(uid(body))
            if not any(ref.name.casefold() == body.name.casefold() for ref in leader.leading):
                result.warnings.append(
                    ParseWarning(
                        line_no=body.line_no,
                        json_path=body.json_path,
                        text=name,
                        reason="leader_one_side",
                    )
                )
        elif len(candidates) == 0:
            result.warnings.append(
                ParseWarning(
                    line_no=body.line_no,
                    json_path=body.json_path,
                    text=name,
                    reason="leader_one_side",
                )
            )
        else:
            result.ambiguities.append(
                Ambiguity(
                    leader_line=None,
                    leader_path=None,
                    leader_name=name,
                    bodyguard_name=body.name,
                    reason="leader_ambiguous",
                )
            )


def _add_pair(result: ParseResult, leader: ParsedUnit, body: ParsedUnit) -> None:
    result.leader_pairs.append(
        LeaderPair(
            leader_line=leader.line_no,
            leader_path=leader.json_path,
            bodyguard_line=body.line_no,
            bodyguard_path=body.json_path,
            leader_name=leader.name,
            bodyguard_name=body.name,
        )
    )
