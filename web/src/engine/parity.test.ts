import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { matchCondition } from "./eligibility";
import { applyEvents, type GameEvent } from "./project";

const root = resolve(__dirname, "../../../fixtures");

describe("paridade de condições", () => {
  const cases = JSON.parse(readFileSync(resolve(root, "conditions/shadow.json"), "utf8").replace(/^\uFEFF/, "")) as {
    name: string;
    node: Record<string, unknown>;
    facts: Record<string, unknown>;
    expected: boolean;
  }[];
  for (const row of cases) {
    it(row.name, () => {
      expect(matchCondition(row.node, row.facts)).toBe(row.expected);
    });
  }
});

describe("paridade de eventos Shadow", () => {
  it("legado e fase batem com o expect da fixture", () => {
    const fixture = JSON.parse(readFileSync(resolve(root, "events/shadow.json"), "utf8").replace(/^\uFEFF/, "")) as {
      events: { seq: number; type: string; payload: Record<string, unknown>; created_at: string }[];
      expect: { warnings_contains: string[]; shadow_count: number; last_nml: boolean; last_opp: boolean };
    };
    const events: GameEvent[] = fixture.events.map((item) => ({
      id: `00000000-0000-4000-8000-${String(item.seq).padStart(12, "0")}`,
      seq: item.seq,
      device_id: "parity",
      type: item.type,
      payload: item.payload,
      created_at: item.created_at,
    }));
    const state = applyEvents(events);
    for (const warning of fixture.expect.warnings_contains) expect(state.warnings).toContain(warning);
    expect(state.shadow.length).toBe(fixture.expect.shadow_count);
    const last = state.shadow[state.shadow.length - 1];
    expect(last.nml_in_shadow).toBe(fixture.expect.last_nml);
    expect(last.opp_dz_in_shadow).toBe(fixture.expect.last_opp);
  });
});
