import type { Moved } from "./eligibility";

const con_lstPhases = ["round_start", "command", "battle_shock", "movement", "shooting", "charge", "fight", "end_of_turn"] as const;
export const PHASES = con_lstPhases;
export const PHASES_V2 = [...con_lstPhases, "end_of_round"] as const;

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
  engaged_at_fight_start: boolean;
  on_action: boolean;
  action_name: string | null;
  battle_shocked: boolean;
  below_half: boolean;
  destroyed: boolean;
  in_reserves: boolean;
  lane: Lane;
  overrides: { key: string }[];
};

const con_lstLanes = ["left", "center", "right", "home"] as const;
export const LANES = con_lstLanes;
export type Lane = (typeof con_lstLanes)[number];

export type ChoiceScope = "turn" | "round" | "battle" | "until_own_command";

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
  stratagem_uses: {
    stratagem_name: string;
    cp_spent: number;
    limit_overridden: boolean;
    phase: string;
    round: number;
    player: string;
    turn_player: string;
    target_list_unit_id?: number | null;
  }[];
  objectives: { objective_label: string; controller: string; round: number }[];
  scores: { player: string; kind: string; label: string; vp: number; round: number }[];
  shadow: {
    round: number;
    turn_player: string;
    phase: string;
    nml_in_shadow: boolean;
    opp_dz_in_shadow: boolean;
    /** legado */
    player?: string;
    objectives_controlled?: number | null;
    whole_board?: boolean | null;
  }[];
  warnings: string[];
  attachments: any[];
  choices: Choice[];
  log: LogEntry[];
  cpLedger: { round: number; turn_player: string; phase: string; player: string; reason: string; delta: number }[];
  eventRules: boolean;
  phasesV: number;
  checklist: { round: number; player: string; key: string; done: boolean }[];
};

export type ShadowNow = { own_dz: true; nml: boolean; opp_dz: boolean; known: boolean };

export function shadowNow(projection: Projection): ShadowNow {
  const var_objRow = projection.shadow.find(
    (item) =>
      item.round === projection.round &&
      item.turn_player === projection.player &&
      item.phase === projection.phase,
  );
  return {
    own_dz: true,
    nml: var_objRow?.nml_in_shadow ?? false,
    opp_dz: var_objRow?.opp_dz_in_shadow ?? false,
    known: !!var_objRow,
  };
}

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
  const var_lstOrdered = [...events].sort(
    (a, b) => a.created_at.localeCompare(b.created_at) || a.device_id.localeCompare(b.device_id) || a.seq - b.seq,
  );
  const var_setInactive = undone(var_lstOrdered);
  const var_objState = empty();
  for (const var_objEvent of var_lstOrdered) {
    const var_boolSkipped = var_setInactive.has(var_objEvent.id) || var_objEvent.type === "undo";
    if (!var_boolSkipped) apply(var_objState, var_objEvent);
    var_objState.log.push({
      id: var_objEvent.id,
      seq: var_objEvent.seq,
      type: var_objEvent.type,
      payload: var_objEvent.payload || {},
      round: var_objState.round,
      player: var_objState.player,
      phase: var_objState.phase,
      undone: var_setInactive.has(var_objEvent.id),
    });
  }
  return var_objState;
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
    cpLedger: [],
    eventRules: false,
    phasesV: 1,
    checklist: [],
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
    engaged_at_fight_start: false,
    on_action: false,
    action_name: null,
    battle_shocked: previous?.battle_shocked ?? false,
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
    state.eventRules = Boolean(payload.event_rules);
    state.phasesV = Number(payload.phases_v || 1);
    for (const unit of payload.units || []) {
      state.live[unit.list_unit_id] = blank(unit.list_unit_id, unit.name || "", 1);
    }
    return;
  }
  if (!state.started) return;
  if (event.type === "game_settings_set") {
    if ("event_rules" in payload) state.eventRules = Boolean(payload.event_rules);
    return;
  }
  if (event.type === "checklist_set") {
    const key = String(payload.key || "");
    const player = payload.player || state.player;
    state.checklist = state.checklist.filter(
      (item) => !(item.round === state.round && item.player === player && item.key === key),
    );
    state.checklist.push({ round: state.round, player, key, done: Boolean(payload.done) });
    return;
  }
  if (event.type === "phase_advanced") {
    let turnedOver = false;
    if (state.phase === "end_of_round") {
      state.round = Math.min(10, state.round + 1);
      state.player = state.firstPlayer;
      state.phase = "round_start";
      turnedOver = true;
    } else {
      const index = PHASES.indexOf(state.phase as (typeof PHASES)[number]);
      if (index >= 0 && index < PHASES.length - 1) {
        state.phase = PHASES[index + 1];
      } else if (state.player !== state.firstPlayer) {
        if (state.phasesV >= 2) {
          state.phase = "end_of_round";
        } else {
          state.round = Math.min(10, state.round + 1);
          state.player = state.firstPlayer;
          state.phase = "round_start";
          turnedOver = true;
        }
      } else {
        state.player = state.player === "me" ? "opponent" : "me";
        // v2: 2º turno vai direto a Command; v1: round_start em cada turno (C17).
        state.phase = state.phasesV >= 2 ? "command" : "round_start";
        turnedOver = true;
      }
    }
    if (turnedOver) {
      for (const [id, prev] of Object.entries(state.live)) {
        state.live[Number(id)] = blank(Number(id), prev.name, state.round, prev);
      }
    }
    if (state.phase === "fight") {
      for (const unit of Object.values(state.live)) {
        unit.engaged_at_fight_start = unit.engaged;
      }
    }
    if (state.phase === "end_of_round" && state.round >= 3) {
      const stuck = Object.values(state.live).some((unit) => unit.in_reserves && !unit.destroyed);
      if (stuck) state.warnings.push("reserves_destroyed");
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
    const scope: ChoiceScope =
      payload.scope === "round" || payload.scope === "battle" || payload.scope === "until_own_command"
        ? payload.scope
        : "turn";
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
    const var_strPlayer = payload.player || state.player;
    const var_intDelta = Number(payload.delta || 0);
    let var_strReason = String(payload.reason || "manual");
    if (var_strReason === "command_phase") var_strReason = "core_cp";
    if (var_strReason === "core_cp" && state.phase === "command") {
      const var_boolTwice = state.cpLedger.some(
        (item) =>
          item.round === state.round &&
          item.turn_player === state.player &&
          item.phase === "command" &&
          item.player === var_strPlayer &&
          item.reason === "core_cp",
      );
      if (var_boolTwice) state.warnings.push("core_cp_twice");
    }
    if (var_intDelta > 0 && var_strReason !== "core_cp" && (state.eventRules || payload.event_rules)) {
      const var_intExtras = state.cpLedger.filter(
        (item) => item.round === state.round && item.player === var_strPlayer && item.delta > 0 && item.reason !== "core_cp",
      ).length;
      if (var_intExtras >= 1) state.warnings.push("extra_cp_cap");
    }
    if (!changeCp(state, var_strPlayer, var_intDelta, Boolean(payload.override))) return;
    state.cpLedger.push({
      round: state.round,
      turn_player: state.player,
      phase: state.phase,
      player: var_strPlayer,
      reason: var_strReason,
      delta: var_intDelta,
    });
    return;
  }
  if (event.type === "stratagem_used") {
    const name = payload.stratagem_name || "Stratagem";
    const player = payload.player === "opponent" ? "opponent" : "me";
    const limit = payload.use_limit || "per_phase";
    const sameName = state.stratagem_uses.filter((item) => item.stratagem_name === name && item.player === player);
    const phaseHit = sameName.some(
      (item) => item.round === state.round && item.phase === state.phase && item.turn_player === state.player,
    );
    if (phaseHit && !payload.limit_overridden) {
      state.warnings.push("stratagem_limit");
      return;
    }
    if (limit !== "none" && limit !== "per_phase" && !payload.limit_overridden) {
      const limitHit =
        limit === "per_battle"
          ? sameName.length > 0
          : limit === "per_round"
            ? sameName.some((item) => item.round === state.round)
            : limit === "per_turn"
              ? sameName.some((item) => item.round === state.round && item.turn_player === state.player)
              : false;
      if (limitHit) {
        state.warnings.push("stratagem_limit");
        return;
      }
    }
    const targetId = payload.target_list_unit_id != null ? Number(payload.target_list_unit_id) : null;
    if (targetId != null) {
      const sameTarget = state.stratagem_uses.some(
        (item) =>
          item.player === player &&
          item.phase === state.phase &&
          item.round === state.round &&
          item.turn_player === state.player &&
          item.target_list_unit_id === targetId,
      );
      if (sameTarget) state.warnings.push("stratagem_same_target");
      const target = state.live[targetId];
      if (target?.battle_shocked) state.warnings.push("stratagem_target_shocked");
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
      turn_player: state.player,
      target_list_unit_id: targetId,
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
    const var_boolLegacy = payload.whole_board !== undefined || payload.objectives_controlled !== undefined;
    const var_strPhase = String(payload.phase || (var_boolLegacy ? "command" : state.phase));
    const var_strTurn = String(payload.turn_player || state.player);
    let var_boolNml = Boolean(payload.nml_in_shadow);
    let var_boolOpp = Boolean(payload.opp_dz_in_shadow);
    if (var_boolLegacy && payload.nml_in_shadow === undefined && payload.opp_dz_in_shadow === undefined) {
      var_boolNml = Boolean(payload.whole_board);
      var_boolOpp = Boolean(payload.whole_board);
      state.warnings.push("shadow_legacy");
    } else {
      if (payload.nml_total != null && payload.nml_controlled != null) {
        const var_intTotal = Number(payload.nml_total);
        const var_intCtrl = Number(payload.nml_controlled);
        var_boolNml = var_intTotal > 0 && var_intCtrl * 2 >= var_intTotal;
      }
      if (payload.opp_dz_total != null && payload.opp_dz_controlled != null) {
        const var_intTotal = Number(payload.opp_dz_total);
        const var_intCtrl = Number(payload.opp_dz_controlled);
        var_boolOpp = var_intTotal > 0 && var_intCtrl * 2 >= var_intTotal;
      }
    }
    state.shadow = state.shadow.filter(
      (item) => !(item.round === state.round && item.turn_player === var_strTurn && item.phase === var_strPhase),
    );
    state.shadow.push({
      round: state.round,
      turn_player: var_strTurn,
      phase: var_strPhase,
      nml_in_shadow: var_boolNml,
      opp_dz_in_shadow: var_boolOpp,
      player: payload.player || "me",
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

export function isChoiceActive(choice: Choice, round: number, player: string, phase?: string): boolean {
  if (choice.scope === "battle") return true;
  if (choice.scope === "round") return choice.round === round;
  if (choice.scope === "until_own_command") {
    if (player !== choice.player || phase !== "command") return true;
    if (round > choice.round) return false;
    return choice.phase === "command";
  }
  return choice.round === round && choice.player === player;
}

export function activeChoice(
  choices: Choice[],
  effectId: number,
  unitId: number | null,
  scope: ChoiceScope,
  round: number,
  player: string,
  phase?: string,
): Choice | undefined {
  return choices.find(
    (item) =>
      item.effect_id === effectId &&
      item.list_unit_id === unitId &&
      isChoiceActive({ ...item, scope }, round, player, phase),
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
