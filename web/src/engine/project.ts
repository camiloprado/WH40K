import type { Moved } from "./eligibility";

export const PHASES = ["round_start", "command", "battle_shock", "movement", "shooting", "charge", "fight", "end_of_turn"] as const;

export type GameEvent = {
  id: string;
  seq: number;
  device_id: string;
  type: string;
  payload: Record<string, any>;
  undoes_event_id?: string | null;
  created_at: string;
};

export type LiveUnit = {
  list_unit_id: number;
  name: string;
  round: number;
  moved: Moved;
  shot: boolean;
  charged: boolean;
  fought: boolean;
  engaged: boolean;
  on_action: boolean;
  action_name: string | null;
  battle_shocked: boolean;
  below_half: boolean;
  destroyed: boolean;
  in_reserves: boolean;
  lane: Lane;
  overrides: { key: string }[];
};

export const LANES = ["left", "center", "right", "home"] as const;
export type Lane = (typeof LANES)[number];

export type ChoiceScope = "turn" | "round" | "battle";

export type Choice = {
  effect_id: number;
  list_unit_id: number | null;
  options: string[];
  scope: ChoiceScope;
  round: number;
  player: string;
  phase: string;
};

export type Projection = {
  status: string;
  result: string | null;
  round: number;
  player: string;
  firstPlayer: string;
  phase: string;
  cp: { me: number; opponent: number };
  vp: { me: number; opponent: number };
  live: Record<number, LiveUnit>;
  stratagem_uses: { stratagem_name: string; cp_spent: number; limit_overridden: boolean; phase: string; round: number; player: string }[];
  objectives: { objective_label: string; controller: string; round: number }[];
  scores: { player: string; kind: string; label: string; vp: number; round: number }[];
  shadow: { round: number; player: string; objectives_controlled: number | null; whole_board: boolean | null }[];
  warnings: string[];
  attachments: any[];
  choices: Choice[];
  log: LogEntry[];
};

export type LogEntry = {
  id: string;
  seq: number;
  type: string;
  payload: Record<string, any>;
  round: number;
  player: string;
  phase: string;
  undone: boolean;
};

export type Zone = "table" | "reserves" | "destroyed";

export function zoneOf(unit: Pick<LiveUnit, "destroyed" | "in_reserves">): Zone {
  if (unit.destroyed) return "destroyed";
  if (unit.in_reserves) return "reserves";
  return "table";
}

export function applyEvents(events: GameEvent[]): Projection {
  const ordered = [...events].sort((a, b) => a.created_at.localeCompare(b.created_at) || a.device_id.localeCompare(b.device_id) || a.seq - b.seq);
  const inactive = undone(ordered);
  const state = empty();
  for (const event of ordered) {
    const skipped = inactive.has(event.id) || event.type === "undo";
    if (!skipped) apply(state, event);
    state.log.push({
      id: event.id,
      seq: event.seq,
      type: event.type,
      payload: event.payload || {},
      round: state.round,
      player: state.player,
      phase: state.phase,
      undone: inactive.has(event.id),
    });
  }
  return state;
}

function undone(events: GameEvent[]): Set<string> {
  let inactive = new Set<string>();
  for (;;) {
    const found = new Set<string>();
    for (const event of events) {
      if (event.type === "undo" && !inactive.has(event.id)) {
        const target = event.undoes_event_id || event.payload.undoes_event_id;
        if (target) found.add(target);
      }
    }
    if (found.size === inactive.size && [...found].every((id) => inactive.has(id))) return inactive;
    inactive = found;
  }
}

function empty(): Projection & { started: boolean } {
  return {
    status: "active",
    result: null as string | null,
    round: 1,
    player: "me",
    firstPlayer: "me",
    phase: "command",
    cp: { me: 0, opponent: 0 },
    vp: { me: 0, opponent: 0 },
    live: {},
    stratagem_uses: [],
    objectives: [],
    scores: [],
    shadow: [],
    warnings: [],
    attachments: [],
    choices: [],
    log: [],
    started: false,
  };
}

function blank(id: number, name: string, round: number, previous?: LiveUnit): LiveUnit {
  return {
    list_unit_id: id,
    name,
    round,
    moved: "none",
    shot: false,
    charged: false,
    fought: false,
    engaged: previous?.engaged ?? false,
    on_action: false,
    action_name: null,
    battle_shocked: false,
    below_half: previous?.below_half ?? false,
    destroyed: previous?.destroyed ?? false,
    in_reserves: previous?.in_reserves ?? false,
    lane: previous?.lane ?? "center",
    overrides: [],
  };
}

function apply(state: Projection & { started: boolean }, event: GameEvent) {
  const payload = event.payload || {};
  if (event.type === "game_started") {
    state.started = true;
    state.firstPlayer = payload.first_player || "me";
    state.player = state.firstPlayer;
    state.phase = "round_start";
    state.round = 1;
    state.cp.me = Number(payload.cp_me || 0);
    state.cp.opponent = Number(payload.cp_opponent || 0);
    state.attachments = payload.attachments || [];
    for (const unit of payload.units || []) {
      state.live[unit.list_unit_id] = blank(unit.list_unit_id, unit.name || "", 1);
    }
    return;
  }
  if (!state.started) return;
  if (event.type === "phase_advanced") {
    const index = PHASES.indexOf(state.phase as (typeof PHASES)[number]);
    let enteredMine = false;
    if (index < PHASES.length - 1) state.phase = PHASES[index + 1];
    else {
      if (state.player !== state.firstPlayer) {
        state.round = Math.min(10, state.round + 1);
        state.player = state.firstPlayer;
      } else state.player = state.player === "me" ? "opponent" : "me";
      state.phase = "round_start";
      enteredMine = state.player === "me";
    }
    if (enteredMine) {
      for (const [id, prev] of Object.entries(state.live)) {
        state.live[Number(id)] = blank(Number(id), prev.name, state.round, prev);
      }
    }
    return;
  }
  if (event.type === "unit_state_set") {
    const unit = state.live[Number(payload.list_unit_id)];
    if (!unit) return;
    const patch = { ...(payload.patch || {}) };
    if ("lane" in patch && !LANES.includes(patch.lane)) {
      delete patch.lane;
      state.warnings.push("bad_lane");
    }
    Object.assign(unit, patch);
    if (payload.overrides) unit.overrides.push(...payload.overrides);
    return;
  }
  if (event.type === "effect_chosen") {
    const scope: ChoiceScope = payload.scope === "round" || payload.scope === "battle" ? payload.scope : "turn";
    const options = (payload.options || []).map(String).slice(0, 12);
    if (payload.count && options.length > Number(payload.count)) state.warnings.push("choice_over_count");
    const row: Choice = {
      effect_id: Number(payload.effect_id),
      list_unit_id: payload.list_unit_id ?? null,
      options,
      scope,
      round: state.round,
      player: payload.player || state.player,
      phase: state.phase,
    };
    state.choices = state.choices.filter((item) => !sameChoice(item, row));
    state.choices.push(row);
    return;
  }
  if (event.type === "cp_changed") {
    changeCp(state, payload.player || state.player, Number(payload.delta || 0), Boolean(payload.override));
    return;
  }
  if (event.type === "stratagem_used") {
    const name = payload.stratagem_name || "Stratagem";
    const player = payload.player || state.player;
    const limit = payload.use_limit || "none";
    const prior = state.stratagem_uses.filter((item) => item.stratagem_name === name && item.player === player && item.phase === state.phase && item.round === state.round);
    if (limit === "per_phase" && prior.length && !payload.limit_overridden) {
      state.warnings.push("stratagem_limit");
      return;
    }
    const spent = Number(payload.cp_spent || 0);
    if (spent && !changeCp(state, player, -spent, Boolean(payload.cp_override))) return;
    state.stratagem_uses.push({
      stratagem_name: name,
      cp_spent: spent,
      limit_overridden: Boolean(payload.limit_overridden),
      phase: state.phase,
      round: state.round,
      player,
    });
    return;
  }
  if (event.type === "objective_set") {
    state.objectives = state.objectives.filter((item) => item.objective_label !== payload.objective_label || item.round !== state.round);
    state.objectives.push({ objective_label: payload.objective_label, controller: payload.controller, round: state.round });
    return;
  }
  if (event.type === "vp_scored") {
    state.scores.push({ player: payload.player || "me", kind: payload.kind || "other", label: payload.label || "", vp: Number(payload.vp || 0), round: state.round });
    state.vp.me = state.scores.filter((item) => item.player === "me").reduce((sum, item) => sum + item.vp, 0);
    state.vp.opponent = state.scores.filter((item) => item.player === "opponent").reduce((sum, item) => sum + item.vp, 0);
    return;
  }
  if (event.type === "shadow_set") {
    const player = payload.player || state.player;
    state.shadow = state.shadow.filter((item) => !(item.round === state.round && item.player === player));
    state.shadow.push({
      round: state.round,
      player,
      objectives_controlled: payload.objectives_controlled ?? null,
      whole_board: payload.whole_board ?? null,
    });
    return;
  }
  if (event.type === "battleshock_result") {
    const unit = state.live[Number(payload.list_unit_id)];
    if (unit) unit.battle_shocked = !payload.passed;
    return;
  }
  if (event.type === "game_ended") {
    state.status = payload.status || "finished";
    if (payload.result === "win" || payload.result === "loss" || payload.result === "draw") state.result = payload.result;
  }
}

function sameChoice(left: Choice, right: Choice): boolean {
  if (left.effect_id !== right.effect_id || left.list_unit_id !== right.list_unit_id) return false;
  if (right.scope === "battle") return true;
  if (right.scope === "round") return left.round === right.round;
  return left.round === right.round && left.player === right.player;
}

export function isChoiceActive(choice: Choice, round: number, player: string): boolean {
  if (choice.scope === "battle") return true;
  if (choice.scope === "round") return choice.round === round;
  return choice.round === round && choice.player === player;
}

export function activeChoice(
  choices: Choice[],
  effectId: number,
  unitId: number | null,
  scope: ChoiceScope,
  round: number,
  player: string,
): Choice | undefined {
  return choices.find(
    (item) =>
      item.effect_id === effectId &&
      item.list_unit_id === unitId &&
      (scope === "battle" || (item.round === round && (scope === "round" || item.player === player))),
  );
}

function changeCp(state: Projection, player: string, delta: number, override: boolean): boolean {
  const key = player === "opponent" ? "opponent" : "me";
  const next = state.cp[key] + delta;
  if (next < 0 && !override) {
    state.warnings.push("cp_blocked");
    return false;
  }
  state.cp[key] = Math.max(0, Math.min(99, next));
  if (next < 0) state.warnings.push("cp_clamped");
  return true;
}
