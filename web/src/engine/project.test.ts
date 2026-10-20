import { expect, it } from "vitest";
import { applyEvents, isChoiceActive, shadowNow, type GameEvent } from "./project";

function ev(seq: number, type: string, payload: Record<string, unknown>, at: string): GameEvent {
  return { id: `00000000-0000-4000-8000-${String(seq).padStart(12, "0")}`, seq, device_id: "device-a", type, payload, created_at: at };
}

it("projeta avanço, CP e undo", () => {
  const start = ev(1, "game_started", { first_player: "me", cp_me: 0, units: [{ list_unit_id: 1, name: "Daemonettes" }] }, "2026-10-15T12:00:00Z");
  const move = ev(2, "unit_state_set", { list_unit_id: 1, patch: { moved: "advanced" } }, "2026-10-15T12:00:01Z");
  const state = applyEvents([
    start,
    ev(3, "cp_changed", { delta: 1, reason: "command_phase", player: "me" }, "2026-10-15T12:00:02Z"),
    ev(4, "phase_advanced", {}, "2026-10-15T12:00:03Z"),
    ev(5, "phase_advanced", {}, "2026-10-15T12:00:04Z"),
    move,
    ev(6, "phase_advanced", {}, "2026-10-15T12:00:05Z"),
    ev(7, "phase_advanced", {}, "2026-10-15T12:00:06Z"),
  ]);
  expect(state.phase).toBe("shooting");
  expect(state.cp.me).toBe(1);
  expect(state.live[1].moved).toBe("advanced");
  const undone = applyEvents([
    start,
    move,
    { ...ev(9, "undo", { undoes_event_id: move.id }, "2026-10-15T12:00:06Z"), undoes_event_id: move.id },
  ]);
  expect(undone.live[1].moved).toBe("none");
  const blocked = applyEvents([start, ev(2, "cp_changed", { delta: -1, player: "me" }, "2026-10-15T12:00:01Z")]);
  expect(blocked.cp.me).toBe(0);
  expect(blocked.warnings).toContain("cp_blocked");
});

it("mantém battle-shock até passar no teste", () => {
  const events = [
    ev(1, "game_started", { first_player: "me", units: [{ list_unit_id: 1, name: "Daemonettes" }] }, "2026-10-15T12:00:00Z"),
    ev(2, "phase_advanced", {}, "2026-10-15T12:00:01Z"),
    ev(3, "battleshock_result", { list_unit_id: 1, passed: false }, "2026-10-15T12:00:02Z"),
  ];
  let seq = 4;
  let state = applyEvents(events);
  for (let step = 0; step < 32; step += 1) {
    events.push(ev(seq, "phase_advanced", {}, `2026-10-15T12:01:${String(seq).padStart(2, "0")}Z`));
    seq += 1;
    state = applyEvents(events);
    if (state.round === 2 && state.player === "me" && state.phase === "command") break;
  }
  expect(state.round).toBe(2);
  expect(state.player).toBe("me");
  expect(state.live[1].battle_shocked).toBe(true);
  const pass = ev(seq, "battleshock_result", { list_unit_id: 1, passed: true }, "2026-10-15T12:02:00Z");
  const cleared = applyEvents([...events, pass]);
  expect(cleared.live[1].battle_shocked).toBe(false);
  const undone = applyEvents([
    ...events,
    pass,
    { ...ev(seq + 1, "undo", { undoes_event_id: pass.id }, "2026-10-15T12:02:01Z"), undoes_event_id: pass.id },
  ]);
  expect(undone.live[1].battle_shocked).toBe(true);
});

it("Gain Core CP e event_rules por partida", () => {
  const start = ev(1, "game_started", { first_player: "me", units: [{ list_unit_id: 1, name: "X" }], event_rules: true }, "2026-10-15T12:00:00Z");
  const meCmd = applyEvents([
    start,
    ev(2, "phase_advanced", {}, "2026-10-15T12:00:01Z"),
    ev(3, "cp_changed", { delta: 1, reason: "core_cp", player: "me" }, "2026-10-15T12:00:02Z"),
    ev(4, "cp_changed", { delta: 1, reason: "core_cp", player: "opponent" }, "2026-10-15T12:00:03Z"),
  ]);
  expect(meCmd.cp).toEqual({ me: 1, opponent: 1 });
  expect(meCmd.eventRules).toBe(true);
  const twice = applyEvents([
    start,
    ev(2, "phase_advanced", {}, "2026-10-15T12:00:01Z"),
    ev(3, "cp_changed", { delta: 1, reason: "core_cp", player: "me" }, "2026-10-15T12:00:02Z"),
    ev(4, "cp_changed", { delta: 1, reason: "core_cp", player: "opponent" }, "2026-10-15T12:00:03Z"),
    ev(5, "cp_changed", { delta: 1, reason: "core_cp", player: "me" }, "2026-10-15T12:00:04Z"),
  ]);
  expect(twice.warnings).toContain("core_cp_twice");
  const extras = applyEvents([
    start,
    ev(2, "phase_advanced", {}, "2026-10-15T12:00:01Z"),
    ev(3, "cp_changed", { delta: 1, reason: "manual", player: "me" }, "2026-10-15T12:00:02Z"),
    ev(4, "cp_changed", { delta: 1, reason: "secondary_discard", player: "me" }, "2026-10-15T12:00:03Z"),
  ]);
  expect(extras.warnings).toContain("extra_cp_cap");
});

it("segundo turno da rodada entra em command sem round_start", () => {
  const events = [ev(1, "game_started", { first_player: "me", units: [{ list_unit_id: 1, name: "X" }] }, "2026-10-15T12:00:00Z")];
  let seq = 2;
  let state = applyEvents(events);
  while (!(state.player === "me" && state.phase === "end_of_turn") && seq < 20) {
    events.push(ev(seq, "phase_advanced", {}, `2026-10-15T12:00:${String(seq).padStart(2, "0")}Z`));
    seq += 1;
    state = applyEvents(events);
  }
  events.push(ev(seq, "phase_advanced", {}, `2026-10-15T12:01:00Z`));
  state = applyEvents(events);
  expect(state.player).toBe("opponent");
  expect(state.phase).toBe("command");
  expect(state.round).toBe(1);
});

it("grava engaged_at_fight_start ao entrar em Fight", () => {
  const events = [
    ev(1, "game_started", { first_player: "me", units: [{ list_unit_id: 1, name: "X" }] }, "2026-10-15T12:00:00Z"),
    ev(2, "unit_state_set", { list_unit_id: 1, patch: { engaged: true } }, "2026-10-15T12:00:01Z"),
  ];
  let seq = 3;
  let state = applyEvents(events);
  while (state.phase !== "fight" && seq < 20) {
    events.push(ev(seq, "phase_advanced", {}, `2026-10-15T12:00:${String(seq).padStart(2, "0")}Z`));
    seq += 1;
    state = applyEvents(events);
  }
  expect(state.phase).toBe("fight");
  expect(state.live[1].engaged_at_fight_start).toBe(true);
  const cleared = applyEvents([
    ...events,
    ev(seq, "unit_state_set", { list_unit_id: 1, patch: { engaged: false } }, "2026-10-15T12:01:00Z"),
  ]);
  expect(cleared.live[1].engaged).toBe(false);
  expect(cleared.live[1].engaged_at_fight_start).toBe(true);
});

it("Shadow por fase e legado whole_board", () => {
  const start = ev(1, "game_started", { first_player: "me", units: [{ list_unit_id: 1, name: "X" }] }, "2026-10-15T12:00:00Z");
  const legacy = applyEvents([
    start,
    ev(2, "shadow_set", { player: "me", objectives_controlled: 2, whole_board: true }, "2026-10-15T12:00:01Z"),
  ]);
  expect(legacy.warnings).toContain("shadow_legacy");
  expect(legacy.shadow[0].phase).toBe("command");
  expect(legacy.shadow[0].nml_in_shadow).toBe(true);
  const phased = applyEvents([
    start,
    ev(2, "phase_advanced", {}, "2026-10-15T12:00:01Z"),
    ev(3, "shadow_set", { nml_controlled: 2, nml_total: 4, opp_dz_controlled: 0, opp_dz_total: 1 }, "2026-10-15T12:00:02Z"),
  ]);
  expect(phased.shadow[0].nml_in_shadow).toBe(true);
  expect(phased.shadow[0].opp_dz_in_shadow).toBe(false);
  expect(shadowNow(phased).known).toBe(true);
  expect(shadowNow(phased).nml).toBe(true);
});

it("C17 phases_v2: end_of_round antes da R2", () => {
  const events = [
    ev(1, "game_started", { first_player: "me", phases_v: 2, units: [{ list_unit_id: 1, name: "X" }] }, "2026-10-15T12:00:00Z"),
  ];
  let seq = 2;
  let state = applyEvents(events);
  while (!(state.player === "opponent" && state.phase === "end_of_turn") && seq < 40) {
    events.push(ev(seq, "phase_advanced", {}, `2026-10-15T12:00:${String(seq).padStart(2, "0")}Z`));
    seq += 1;
    state = applyEvents(events);
  }
  events.push(ev(seq, "phase_advanced", {}, "2026-10-15T12:01:00Z"));
  state = applyEvents(events);
  expect(state.phase).toBe("end_of_round");
  expect(state.round).toBe(1);
  events.push(ev(seq + 1, "phase_advanced", {}, "2026-10-15T12:01:01Z"));
  state = applyEvents(events);
  expect(state.phase).toBe("round_start");
  expect(state.round).toBe(2);
  expect(state.player).toBe("me");
});

it("C17 phases_v1: sem end_of_round (byte-compat)", () => {
  const events = [ev(1, "game_started", { first_player: "me", units: [{ list_unit_id: 1, name: "X" }] }, "2026-10-15T12:00:00Z")];
  let seq = 2;
  let state = applyEvents(events);
  while (!(state.player === "opponent" && state.phase === "end_of_turn") && seq < 40) {
    events.push(ev(seq, "phase_advanced", {}, `2026-10-15T12:00:${String(seq).padStart(2, "0")}Z`));
    seq += 1;
    state = applyEvents(events);
  }
  events.push(ev(seq, "phase_advanced", {}, "2026-10-15T12:01:00Z"));
  state = applyEvents(events);
  expect(state.phase).toBe("round_start");
  expect(state.round).toBe(2);
  expect(state.phasesV).toBe(1);
});

it("C10 zera fought ao trocar para o turno do oponente", () => {
  const events = [
    ev(1, "game_started", { first_player: "me", units: [{ list_unit_id: 1, name: "X" }] }, "2026-10-15T12:00:00Z"),
    ev(2, "unit_state_set", { list_unit_id: 1, patch: { engaged: true, fought: true } }, "2026-10-15T12:00:01Z"),
  ];
  let seq = 3;
  let state = applyEvents(events);
  while (!(state.player === "opponent" && state.phase === "fight") && seq < 40) {
    events.push(ev(seq, "phase_advanced", {}, `2026-10-15T12:00:${String(seq).padStart(2, "0")}Z`));
    seq += 1;
    state = applyEvents(events);
  }
  expect(state.player).toBe("opponent");
  expect(state.phase).toBe("fight");
  expect(state.live[1].fought).toBe(false);
  expect(state.live[1].engaged).toBe(true);
});

it("C12 per_turn não avisa entre turnos da mesma rodada", () => {
  const events = [
    ev(1, "game_started", { first_player: "me", cp_me: 3, units: [{ list_unit_id: 1, name: "X" }] }, "2026-10-15T12:00:00Z"),
    ev(
      2,
      "stratagem_used",
      { stratagem_name: "Fire Overwatch", cp_spent: 1, use_limit: "per_turn", player: "me" },
      "2026-10-15T12:00:01Z",
    ),
  ];
  let seq = 3;
  let state = applyEvents(events);
  while (!(state.player === "opponent" && state.phase === "command") && seq < 30) {
    events.push(ev(seq, "phase_advanced", {}, `2026-10-15T12:00:${String(seq).padStart(2, "0")}Z`));
    seq += 1;
    state = applyEvents(events);
  }
  events.push(
    ev(
      seq,
      "stratagem_used",
      { stratagem_name: "Fire Overwatch", cp_spent: 1, use_limit: "per_turn", player: "me" },
      "2026-10-15T12:01:00Z",
    ),
  );
  state = applyEvents(events);
  expect(state.warnings).not.toContain("stratagem_limit");
  expect(state.stratagem_uses).toHaveLength(2);
  expect(state.cp.me).toBe(1);
});

it("guarda a faixa entre turnos e troca a escolha do efeito no mesmo turno", () => {
  const events = [
    ev(1, "game_started", { first_player: "me", units: [{ list_unit_id: 1, name: "Lion" }] }, "2026-10-15T12:00:00Z"),
    ev(2, "unit_state_set", { list_unit_id: 1, patch: { lane: "home" } }, "2026-10-15T12:00:01Z"),
    ev(3, "effect_chosen", { effect_id: 7, list_unit_id: 1, options: ["A", "B"], count: 2 }, "2026-10-15T12:00:02Z"),
    ev(4, "effect_chosen", { effect_id: 7, list_unit_id: 1, options: ["B", "C"], count: 2 }, "2026-10-15T12:00:03Z"),
    ev(5, "effect_chosen", { effect_id: 8, options: ["Vow"], scope: "battle" }, "2026-10-15T12:00:04Z"),
  ];
  for (let index = 6; index < 24; index += 1) events.push(ev(index, "phase_advanced", {}, `2026-10-15T12:00:${String(index).padStart(2, "0")}Z`));
  const state = applyEvents(events);
  expect(state.round).toBe(2);
  expect(state.live[1].lane).toBe("home");
  expect(state.choices.map((item) => item.options)).toEqual([["B", "C"], ["Vow"]]);
  expect(isChoiceActive(state.choices[0], state.round, state.player)).toBe(false);
  expect(isChoiceActive(state.choices[1], state.round, state.player)).toBe(true);
});
