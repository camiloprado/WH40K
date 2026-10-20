import { expect, it } from "vitest";
import { applyEvents, type GameEvent } from "./project";

const ev = (seq: number, type: string, payload: Record<string, unknown>, created_at: string): GameEvent => ({
  id: `00000000-0000-4000-8000-${String(seq).padStart(12, "0")}`,
  seq,
  device_id: "t",
  type,
  payload,
  created_at,
});

it("C14 reserves_over_50 e must_ingress via Realm of Chaos", () => {
  const over = applyEvents([
    ev(
      1,
      "game_started",
      {
        first_player: "me",
        phases_v: 2,
        total_points: 1975,
        units: [
          { list_unit_id: 1, name: "A", in_reserves: true, points: 1000 },
          { list_unit_id: 2, name: "B", points: 975 },
        ],
      },
      "2026-10-15T12:00:00Z",
    ),
  ]);
  expect(over.warnings).toContain("reserves_over_50");

  const events = [
    ev(
      1,
      "game_started",
      {
        first_player: "opponent",
        phases_v: 2,
        cp_me: 2,
        units: [{ list_unit_id: 1, name: "Daemonettes" }],
      },
      "2026-10-15T12:00:00Z",
    ),
    ev(2, "unit_state_set", { list_unit_id: 1, patch: { engaged: true } }, "2026-10-15T12:00:01Z"),
    ev(
      3,
      "stratagem_used",
      {
        stratagem_name: "The Realm of Chaos",
        cp_spent: 1,
        player: "me",
        target_list_unit_id: 1,
      },
      "2026-10-15T12:00:02Z",
    ),
  ];
  const state = applyEvents(events);
  expect(state.warnings).toContain("stratagem_target_engaged");
  expect(state.live[1].in_reserves).toBe(true);
  expect(state.live[1].must_ingress).toBe(true);
});
