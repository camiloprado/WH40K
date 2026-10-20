import { readFileSync, readdirSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { describe, expect, it } from "vitest";
import { applyEvents, type GameEvent } from "./project";

const root = join(dirname(fileURLToPath(import.meta.url)), "../../../fixtures/events");

function readJson(path: string) {
  const text = readFileSync(path, "utf8").replace(/^\uFEFF/, "");
  return JSON.parse(text);
}

function normalize(events: Record<string, unknown>[]): GameEvent[] {
  return events.map((item, index) => ({
    id: String(item.id || `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`),
    seq: Number(item.seq || index + 1),
    device_id: String(item.device_id || "fixture"),
    type: String(item.type),
    payload: (item.payload || {}) as Record<string, unknown>,
    created_at: String(item.created_at || "2026-10-15T12:00:00Z"),
  }));
}

describe("Q4 fixtures/events no Vitest", () => {
  const files = readdirSync(root).filter((name: string) => name.endsWith(".json") && !name.includes(".local."));
  for (const name of files) {
    it(name, () => {
      const raw = readJson(join(root, name));
      const state = applyEvents(normalize(raw.events || raw));
      expect(state.round).toBeGreaterThanOrEqual(1);
      const exp = raw.expect;
      if (!exp) return;
      if (exp.uses != null) expect(state.stratagem_uses.length).toBe(exp.uses);
      if (exp.cp_me != null) expect(state.cp.me).toBe(exp.cp_me);
      if (exp.no_warning) expect(state.warnings).not.toContain(exp.no_warning);
      if (exp.warning) expect(state.warnings).toContain(exp.warning);
      if (exp.phase) expect(state.phase).toBe(exp.phase);
      if (exp.round) expect(state.round).toBe(exp.round);
      if (exp.player) expect(state.player).toBe(exp.player);
    });
  }
});
