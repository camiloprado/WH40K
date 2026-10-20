import { describe, expect, it } from "vitest";
import { matchCondition } from "./eligibility";
import { applyEvents, type GameEvent } from "./project";

const conditionCases = [
  { name: "own_dz_only_true_is_false", node: { "game.shadow_of_chaos": true }, facts: { shadow_areas: ["own_dz"] }, expected: false },
  { name: "own_dz_only_false_is_true", node: { "game.shadow_of_chaos": false }, facts: { shadow_areas: ["own_dz"] }, expected: true },
  { name: "own_dz_area", node: { "game.shadow_of_chaos": "own_dz" }, facts: { shadow_areas: ["own_dz"] }, expected: true },
  { name: "nml_makes_true", node: { "game.shadow_of_chaos": true }, facts: { shadow_areas: ["own_dz", "nml"] }, expected: true },
  { name: "unknown_fact", node: { xyz: 1 }, facts: {}, expected: false },
  { name: "turn_owner_own", node: { turn_owner: "own" }, facts: { turn_owner: "own" }, expected: true },
  { name: "turn_owner_mismatch", node: { turn_owner: "opponent" }, facts: { turn_owner: "own" }, expected: false },
];

describe("paridade de condições", () => {
  for (const row of conditionCases) {
    it(row.name, () => {
      expect(matchCondition(row.node as Record<string, unknown>, row.facts)).toBe(row.expected);
    });
  }
});

describe("paridade de eventos Shadow", () => {
  it("legado e fase batem com o expect da fixture", () => {
    const events: GameEvent[] = [
      { id: "00000000-0000-4000-8000-000000000001", seq: 1, device_id: "parity", type: "game_started", payload: { first_player: "me", units: [{ list_unit_id: 1, name: "X" }] }, created_at: "2026-10-15T12:00:00Z" },
      { id: "00000000-0000-4000-8000-000000000002", seq: 2, device_id: "parity", type: "shadow_set", payload: { player: "me", objectives_controlled: 2, whole_board: true }, created_at: "2026-10-15T12:00:01Z" },
      { id: "00000000-0000-4000-8000-000000000003", seq: 3, device_id: "parity", type: "phase_advanced", payload: {}, created_at: "2026-10-15T12:00:02Z" },
      { id: "00000000-0000-4000-8000-000000000004", seq: 4, device_id: "parity", type: "phase_advanced", payload: {}, created_at: "2026-10-15T12:00:03Z" },
      { id: "00000000-0000-4000-8000-000000000005", seq: 5, device_id: "parity", type: "phase_advanced", payload: {}, created_at: "2026-10-15T12:00:04Z" },
      { id: "00000000-0000-4000-8000-000000000006", seq: 6, device_id: "parity", type: "shadow_set", payload: { nml_controlled: 2, nml_total: 4, opp_dz_controlled: 0, opp_dz_total: 1 }, created_at: "2026-10-15T12:00:05Z" },
    ];
    const state = applyEvents(events);
    expect(state.warnings).toContain("shadow_legacy");
    expect(state.shadow.length).toBe(2);
    const last = state.shadow[state.shadow.length - 1];
    expect(last.nml_in_shadow).toBe(true);
    expect(last.opp_dz_in_shadow).toBe(false);
  });
});
