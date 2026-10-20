export type Moved = "none" | "normal" | "advanced" | "fell_back" | "remained";

export type UnitSnapshot = {
  moved: Moved;
  shot: boolean;
  charged: boolean;
  fought: boolean;
  engaged: boolean;
  engaged_at_fight_start?: boolean;
  on_action: boolean;
  battle_shocked: boolean;
  destroyed: boolean;
  in_reserves?: boolean;
  /** C14 / Realm of Chaos: deve fazer ingress no próximo Movement. */
  must_ingress?: boolean;
  below_half?: boolean;
  /** C15: moved no instante em que a ação começou. */
  action_started_moved?: Moved | null;
  /** C15/C11: usou Fire Overwatch (snap shooting). */
  snap_shooting?: boolean;
  /** N8: ordered | desperate */
  fall_back_mode?: "ordered" | "desperate" | null;
  overrides?: { key: string }[];
};

export type WeaponRef = { name: string; keywords?: string[]; kind?: string };

export type RuleEffect = {
  effect_kind: string;
  restriction_key?: string | null;
  condition_json?: Record<string, unknown>;
  ability_name?: string;
  phase?: string;
};

export type Eligibility = {
  status: "active" | "inactive" | "done" | "warn";
  reasons: string[];
  allowedWeapons: string[];
  destroyed: boolean;
};

const con_dctPhaseDone: Record<string, { flag: keyof UnitSnapshot; label: string }> = {
  movement: { flag: "moved", label: "Já moveu" },
  shooting: { flag: "shot", label: "Já atirou" },
  charge: { flag: "charged", label: "Já carregou" },
  fight: { flag: "fought", label: "Já lutou" },
};

/** Compat: testes/legado podem referenciar DONE. */
export const DONE = con_dctPhaseDone;

const con_strCloseQuarters = "CLOSE-QUARTERS";
const con_strPistol = "PISTOL";
const con_strAssault = "ASSAULT";
const con_strBlast = "BLAST";

export type GameFacts = {
  round?: number;
  shadow?: string[];
  /** true quando nml/opp_dz foram informados nesta fase. */
  shadowComplete?: boolean;
  turnOwner?: "own" | "opponent";
  isLeading?: boolean;
  firstPlayer?: "me" | "opponent";
  /** Keywords da unidade (Deep Strike / Warp Rifts) para razões de ingress. */
  hasDeepStrike?: boolean;
  hasWarpRifts?: boolean;
};

export function canStartAction(
  unit: UnitSnapshot,
  unitKeywords?: string[],
  opts?: { oc?: number | null | string; snapShooting?: boolean },
): string[] {
  const var_lstReasons: string[] = [];
  const var_setOverrides = new Set((unit.overrides ?? []).map((item) => item.key));
  const var_boolTitanic = (unitKeywords ?? []).some((item) => item.toUpperCase() === "TITANIC");
  if (unit.destroyed || unit.in_reserves) var_lstReasons.push("Fora do tabuleiro: não começa ação");
  if ((unitKeywords ?? []).some((item) => ["AIRCRAFT", "FORTIFICATION"].includes(item.toUpperCase()))) {
    var_lstReasons.push("AIRCRAFT/FORTIFICATION: não começa ação");
  }
  if (unit.battle_shocked) var_lstReasons.push("Em battle-shock: não começa ação");
  const var_mixOc = opts?.oc;
  // OC null = desconhecido: não bloqueia (C15).
  if (var_mixOc === 0 || var_mixOc === "–" || var_mixOc === "-") {
    var_lstReasons.push("OC 0/–: não começa ação");
  }
  if (unit.engaged && !var_boolTitanic) var_lstReasons.push("Engajada: não começa ação");
  if (unit.moved === "advanced" && !var_setOverrides.has("action_after_advance")) {
    var_lstReasons.push("Avançou: não começa ação neste turno");
  }
  if (unit.moved === "fell_back" && !var_setOverrides.has("action_after_fall_back")) {
    var_lstReasons.push("Recuou: não começa ação neste turno");
  }
  if (opts?.snapShooting) var_lstReasons.push("Fez snap shooting: não começa ação nesta fase");
  if (unit.on_action) var_lstReasons.push("Já começou outra ação neste turno");
  return var_lstReasons;
}

export function evaluateUnit(input: {
  phase: string;
  unit: UnitSnapshot;
  weapons?: WeaponRef[];
  unitKeywords?: string[];
  effects?: RuleEffect[];
  game?: GameFacts;
  activePlayer?: "me" | "opponent";
}): Eligibility {
  const var_lstWeapons = input.weapons ?? [];
  const var_lstNames = var_lstWeapons.map((item) => item.name);
  const var_setOverrides = new Set((input.unit.overrides ?? []).map((item) => item.key));
  const var_setAllows = new Set<string>();
  const var_setDenies = new Set<string>();
  const var_lstWeaponFilters: string[] = [];
  for (const var_objEffect of input.effects ?? []) {
    if (!matches(var_objEffect.condition_json ?? {}, input)) continue;
    if (!var_objEffect.restriction_key) continue;
    if (var_objEffect.effect_kind === "allow") {
      var_setAllows.add(var_objEffect.restriction_key);
      const var_strFilter = keywordFilter(var_objEffect.condition_json);
      if (var_strFilter) var_lstWeaponFilters.push(var_strFilter);
    }
    if (var_objEffect.effect_kind === "deny") var_setDenies.add(var_objEffect.restriction_key);
  }
  const var_fnPermitted = (key: string) =>
    (var_setAllows.has(key) || var_setOverrides.has(key)) && !var_setDenies.has(key);
  if (input.unit.destroyed || var_setDenies.has("destroyed")) {
    return { status: "inactive", reasons: ["Destruída"], allowedWeapons: [], destroyed: true };
  }
  if (input.unit.in_reserves) {
    return reservesEligibility(input);
  }
  const var_strActive = input.activePlayer ?? "me";
  const var_setReactive = new Set(["overwatch", "heroic_intervention", "rapid_ingress", "reactive_move"]);
  // Overwatch só na Movement do oponente (Core 15.08 / C11); no Shooting fica inactive.
  const var_boolReactive = [...var_setReactive].some((key) => {
    if (key === "overwatch" && input.phase !== "movement") return false;
    return var_fnPermitted(key);
  });
  if (
    var_strActive === "opponent" &&
    (input.phase === "movement" || input.phase === "shooting" || input.phase === "charge") &&
    !var_boolReactive
  ) {
    return {
      status: "inactive",
      reasons: ["Turno do oponente"],
      allowedWeapons: [],
      destroyed: false,
    };
  }
  if (input.phase === "shooting" && !hasRanged(var_lstWeapons)) {
    return { status: "done", reasons: ["Sem arma de tiro"], allowedWeapons: [], destroyed: false };
  }
  // N8: lembretes de Movement antes do short-circuit de phaseDone.
  const var_lstMoveHints: string[] = [];
  if (input.phase === "movement") {
    if (input.unit.engaged && input.unit.moved === "none") {
      var_lstMoveHints.push("Engajada: fica parada ou recua");
    }
    if (input.unit.engaged && input.unit.battle_shocked && input.unit.moved === "none") {
      var_lstMoveHints.push(
        "Em battle-shock: se recuar, só Desperate Escape — hazard roll por modelo (1–2 = mortal wound)",
      );
    }
    if (
      input.unit.engaged &&
      !input.unit.battle_shocked &&
      input.unit.moved === "fell_back" &&
      input.unit.fall_back_mode === "desperate"
    ) {
      var_lstMoveHints.push(
        "Desperate Escape: hazard roll por modelo e teste de battle-shock depois de mover",
      );
    }
  }
  const var_strDoneEarly = phaseDone(input.phase, input.unit);
  if (var_strDoneEarly) {
    return {
      status: "done",
      reasons: [...var_lstMoveHints, var_strDoneEarly],
      allowedWeapons: var_lstNames,
      destroyed: false,
    };
  }
  const var_lstReasons: string[] = [...var_lstMoveHints];
  let var_lstAllowed = var_lstNames;
  let var_boolInactive = false;
  if (var_boolReactive && var_strActive === "opponent") {
    var_lstReasons.push("Permitido por regra no turno do oponente");
  }
  if (input.phase === "shooting") {
    const var_boolMonsterVehicle = (input.unitKeywords ?? []).some(
      (item) => item.toUpperCase() === "MONSTER" || item.toUpperCase() === "VEHICLE",
    );
    if (input.unit.engaged && var_fnPermitted("shoot_engaged")) {
      var_lstReasons.push("Permitido por regra");
    } else if (input.unit.engaged) {
      if (input.unit.moved === "advanced") {
        var_boolInactive = true;
        var_lstAllowed = [];
        var_lstReasons.push("Engajada e avançou — sem tiro");
      } else if (!var_boolMonsterVehicle) {
        const var_lstClose = var_lstWeapons
          .filter((item) => isCloseQuarters(item))
          .filter((item) => !keywordsOf(item).includes(con_strBlast))
          .map((item) => item.name);
        if (var_lstClose.length === 0) {
          var_boolInactive = true;
          var_lstAllowed = [];
          var_lstReasons.push("Em combate — sem arma CLOSE-QUARTERS");
        } else {
          var_lstAllowed = var_lstClose;
          var_lstReasons.push("Só CLOSE-QUARTERS / PISTOL, só contra quem está engajado com ela");
        }
      } else {
        const var_lstNonCq = var_lstWeapons.filter((item) => !isCloseQuarters(item)).map((item) => item.name);
        const var_lstBlast = var_lstWeapons
          .filter((item) => keywordsOf(item).includes(con_strBlast))
          .map((item) => item.name);
        var_lstReasons.push(
          "MONSTER/VEHICLE engajado: −1 para acertar, exceto CLOSE-QUARTERS contra quem está engajado com ela",
        );
        if (var_lstNonCq.length) var_lstReasons.push(`−1 para acertar com: ${var_lstNonCq.join(", ")}`);
        if (var_lstBlast.length) {
          var_lstReasons.push(`BLAST não mira a unidade engajada: ${var_lstBlast.join(", ")}`);
        }
      }
    } else {
      if (input.unit.moved === "advanced" && !var_fnPermitted("shoot_after_advance")) {
        const var_lstAssault = var_lstWeapons
          .filter((item) => keywordsOf(item).includes(con_strAssault))
          .map((item) => item.name);
        if (var_lstAssault.length === 0) {
          var_boolInactive = true;
          var_lstReasons.push("Avançou — sem ASSAULT");
          var_lstAllowed = [];
        } else {
          var_lstAllowed = var_lstAssault;
          var_lstReasons.push("Só armas ASSAULT");
        }
      } else if (input.unit.moved === "advanced" && var_fnPermitted("shoot_after_advance")) {
        var_lstReasons.push("Permitido por regra");
        if (var_lstWeaponFilters.length) {
          var_lstAllowed = var_lstWeapons
            .filter((item) => var_lstWeaponFilters.every((key) => (item.keywords ?? []).includes(key)))
            .map((item) => item.name);
          if (var_lstAllowed.length === 0) {
            var_boolInactive = true;
            var_lstReasons.push("Avançou — sem ASSAULT");
          }
        }
      }
    }
    if (input.unit.moved === "fell_back" && !var_fnPermitted("shoot_after_fall_back")) {
      var_boolInactive = true;
      var_lstReasons.push("Recuou");
      var_lstAllowed = [];
    } else if (input.unit.moved === "fell_back" && var_fnPermitted("shoot_after_fall_back")) {
      var_lstReasons.push("Permitido por regra");
    }
    if (
      input.unit.on_action &&
      !var_fnPermitted("shoot_on_action") &&
      !(input.unitKeywords ?? []).some((item) => item.toUpperCase() === "TITANIC")
    ) {
      var_boolInactive = true;
      var_lstReasons.push("Em ação");
      var_lstAllowed = [];
    }
  }
  if (input.phase === "charge") {
    if (input.unit.engaged) {
      var_boolInactive = true;
      var_lstReasons.push("Já está em combate");
    }
    if (
      (input.unit.moved === "advanced" && !var_fnPermitted("charge_after_advance")) ||
      (input.unit.moved === "fell_back" && !var_fnPermitted("charge_after_fall_back"))
    ) {
      var_boolInactive = true;
      var_lstReasons.push(input.unit.moved === "advanced" ? "Avançou" : "Recuou");
    } else if (input.unit.moved === "advanced" || input.unit.moved === "fell_back") {
      var_lstReasons.push("Permitido por regra");
    }
    if (input.unit.on_action) {
      var_boolInactive = true;
      var_lstReasons.push("Em ação");
    }
  }
  if (input.phase === "fight") {
    const var_boolWasEngaged = !!input.unit.engaged_at_fight_start;
    const var_boolCanFight =
      input.unit.engaged || input.unit.charged || var_boolWasEngaged || var_fnPermitted("fight_again");
    if (!var_boolCanFight) {
      var_boolInactive = true;
      var_lstReasons.push("Não está em combate");
    } else if (!input.unit.engaged && (input.unit.charged || var_boolWasEngaged)) {
      var_lstReasons.push("Overrun fight: pile-in extra antes de lutar");
    }
  }
  if (input.unit.moved === "advanced" || input.unit.moved === "fell_back") {
    const var_strKey = input.unit.moved === "advanced" ? "action_after_advance" : "action_after_fall_back";
    if (!var_fnPermitted(var_strKey)) {
      var_lstReasons.push(
        input.unit.moved === "advanced"
          ? "Avançou: não começa ação neste turno"
          : "Recuou: não começa ação neste turno",
      );
    }
  }
  if (input.unit.on_action) {
    for (const var_strReason of canStartAction(
      { ...input.unit, on_action: false },
      input.unitKeywords,
      { snapShooting: Boolean(input.unit.snap_shooting) },
    )) {
      if (!var_lstReasons.includes(var_strReason)) var_lstReasons.push(var_strReason);
    }
    const var_strStarted = input.unit.action_started_moved ?? "none";
    if (input.unit.moved !== var_strStarted) {
      var_lstReasons.push("Ação não conclui: moveu depois de começar");
    }
  }
  if (
    input.phase === "shooting" &&
    !input.unit.engaged &&
    !(input.unitKeywords ?? []).some((item) => item.toUpperCase() === "MONSTER" || item.toUpperCase() === "VEHICLE")
  ) {
    const var_boolHasCq = var_lstWeapons.some((item) => isCloseQuarters(item));
    const var_boolHasOther = var_lstWeapons.some(
      (item) => (item.kind === "ranged" || (item.kind !== "melee" && item.kind !== "wargear")) && !isCloseQuarters(item),
    );
    if (var_boolHasCq && var_boolHasOther) {
      var_lstReasons.push("Escolha: CLOSE-QUARTERS ou as outras armas");
    }
  }
  if (
    input.unit.shot &&
    (input.unit.moved === "advanced" || input.unit.engaged) &&
    (input.phase === "shooting" || input.phase === "charge" || input.phase === "fight")
  ) {
    var_lstReasons.push("Atirou: não começa ação nesta fase");
  }
  if (input.unit.battle_shocked) {
    var_lstReasons.push(
      "Battle-shock: OC vira traço, não pode ser alvo de stratagem nem começar ou concluir ação",
    );
  }
  const var_strDone = phaseDone(input.phase, input.unit);
  if (var_strDone && !var_boolInactive) {
    return {
      status: "done",
      reasons: [var_strDone, ...var_lstReasons],
      allowedWeapons: var_lstAllowed,
      destroyed: false,
    };
  }
  if (var_boolInactive) {
    return { status: "inactive", reasons: var_lstReasons, allowedWeapons: var_lstAllowed, destroyed: false };
  }
  if (input.unit.battle_shocked && input.phase !== "battle_shock") {
    return { status: "warn", reasons: var_lstReasons, allowedWeapons: var_lstAllowed, destroyed: false };
  }
  return { status: "active", reasons: var_lstReasons, allowedWeapons: var_lstAllowed, destroyed: false };
}

function keywordsOf(weapon: WeaponRef): string[] {
  return (weapon.keywords ?? []).map((item) => item.toUpperCase());
}

function isCloseQuarters(weapon: WeaponRef): boolean {
  const var_lstKeys = keywordsOf(weapon);
  return var_lstKeys.includes(con_strCloseQuarters) || var_lstKeys.includes(con_strPistol);
}

function hasRanged(weapons: WeaponRef[]): boolean {
  if (weapons.length === 0) return false;
  return weapons.some((item) => item.kind === "ranged" || (item.kind !== "melee" && item.kind !== "wargear"));
}

function phaseDone(phase: string, unit: UnitSnapshot): string | null {
  if (phase === "movement" && unit.moved !== "none") return "Já moveu";
  if (phase === "shooting" && unit.shot) return "Já atirou";
  if (phase === "charge" && unit.charged) return "Já carregou";
  if (phase === "fight" && unit.fought) return "Já lutou";
  return null;
}

function keywordFilter(node: Record<string, unknown> | undefined): string | null {
  if (!node) return null;
  if (typeof node.weapon_keyword === "string") return node.weapon_keyword;
  for (const var_strKey of ["all", "any"] as const) {
    const var_lstChildren = node[var_strKey];
    if (Array.isArray(var_lstChildren)) {
      for (const var_objChild of var_lstChildren) {
        const var_strFound = keywordFilter(var_objChild as Record<string, unknown>);
        if (var_strFound) return var_strFound;
      }
    }
  }
  return null;
}

/** Avalia condition_json contra fatos de jogo (paridade com condition.matches). */
export function matchCondition(
  node: Record<string, unknown>,
  facts: {
    shadow_areas?: string[];
    shadow_areas_complete?: boolean;
    turn_owner?: string;
    is_leading?: boolean;
    round?: number;
    [key: string]: unknown;
  },
): boolean {
  return matches(node, {
    phase: String(facts.phase || "command"),
    unit: {
      moved: "none",
      shot: false,
      charged: false,
      fought: false,
      engaged: false,
      on_action: false,
      battle_shocked: false,
      destroyed: false,
    },
    game: {
      round: facts.round as number | undefined,
      turnOwner: facts.turn_owner as "own" | "opponent" | undefined,
      isLeading: Boolean(facts.is_leading),
      shadow: facts.shadow_areas as string[] | undefined,
      shadowComplete: Boolean(facts.shadow_areas_complete),
    },
  });
}

function shadowUnevaluable(expected: unknown, areas: string[], complete: boolean): boolean {
  if (complete) return false;
  if (expected === true || expected === false) return true;
  const area = String(expected);
  if (area === "nml" || area === "opp_dz") return !areas.includes(area);
  return false;
}

function conditionUnevaluable(
  node: Record<string, unknown>,
  facts: { shadow_areas?: string[]; shadow_areas_complete?: boolean },
): boolean {
  if (!node || Object.keys(node).length === 0) return false;
  if (Array.isArray(node.all)) return node.all.some((child) => conditionUnevaluable(child as Record<string, unknown>, facts));
  if (Array.isArray(node.any)) return node.any.some((child) => conditionUnevaluable(child as Record<string, unknown>, facts));
  if (node.not) return conditionUnevaluable(node.not as Record<string, unknown>, facts);
  const [key, expected] = Object.entries(node)[0];
  if (key === "game.shadow_of_chaos") {
    return shadowUnevaluable(expected, facts.shadow_areas || [], Boolean(facts.shadow_areas_complete));
  }
  return false;
}

export function conditionLabel(node: Record<string, unknown> | null | undefined): string {
  if (!node || Object.keys(node).length === 0) return "";
  if (Array.isArray(node.all)) return node.all.map((child) => conditionLabel(child as Record<string, unknown>)).join(" e ");
  if (Array.isArray(node.any)) return node.any.map((child) => conditionLabel(child as Record<string, unknown>)).join(" ou ");
  if (node.not) return `não (${conditionLabel(node.not as Record<string, unknown>)})`;
  const [key, expected] = Object.entries(node)[0];
  if (key === "game.shadow_of_chaos") {
    if (expected === true) return "Shadow ativo (TdN ou DZ do oponente)";
    if (expected === false) return "Shadow só na própria DZ";
    return `Shadow: ${expected}`;
  }
  return `${key}=${expected}`;
}

/** Guia/lembrete: fato não avaliável não filtra (R1). Elegibilidade allow/deny usa matchCondition (M6). */
export function guideMatch(
  node: Record<string, unknown> | null | undefined,
  facts: { shadow_areas?: string[]; shadow_areas_complete?: boolean; turn_owner?: string; phase?: string; [key: string]: unknown },
): { include: boolean; conditional: boolean } {
  if (!node || Object.keys(node).length === 0) return { include: true, conditional: false };
  if (matchCondition(node, facts)) return { include: true, conditional: false };
  if (conditionUnevaluable(node, facts)) return { include: true, conditional: true };
  return { include: false, conditional: false };
}

function reservesEligibility(input: {
  phase: string;
  unit: UnitSnapshot;
  unitKeywords?: string[];
  game?: GameFacts;
}): Eligibility {
  const round = input.game?.round ?? 1;
  const must = Boolean(input.unit.must_ingress);
  const opponentFirst = input.game?.firstPlayer === "opponent";
  const earlyOk = must && opponentFirst;
  if (round <= 1 && !earlyOk) {
    return {
      status: "inactive",
      reasons: ["Reserva: entra a partir da rodada 2"],
      allowedWeapons: [],
      destroyed: false,
    };
  }
  const reasons = ingressReasons(input.unitKeywords, input.game, round);
  if (must) reasons.unshift("Realm of Chaos: deve fazer ingress neste Movement");
  return { status: "warn", reasons, allowedWeapons: [], destroyed: false };
}

function ingressReasons(
  unitKeywords: string[] | undefined,
  game: GameFacts | undefined,
  round: number,
): string[] {
  const keys = (unitKeywords ?? []).map((item) => item.toUpperCase());
  const deep = Boolean(game?.hasDeepStrike) || keys.includes("DEEP STRIKE");
  const warp = Boolean(game?.hasWarpRifts) || keys.includes("WARP RIFTS");
  const reasons: string[] = [];
  if (warp) {
    reasons.push('Ingress Warp Rifts: >6" se inteira no Shadow ou a 6" de Greater Daemon do mesmo deus');
  } else if (deep) {
    reasons.push('Ingress Deep Strike: >8" dos inimigos');
  } else {
    reasons.push('Ingress: 6" da borda e >8" dos inimigos');
  }
  if (round < 3) {
    reasons.push("R2: não na zona do oponente antes da R3");
  }
  return reasons;
}

function matches(
  node: Record<string, unknown>,
  input: {
    phase: string;
    unit: UnitSnapshot;
    weapons?: WeaponRef[];
    unitKeywords?: string[];
    game?: GameFacts;
  },
): boolean {
  if (!node || Object.keys(node).length === 0) return true;
  if (Array.isArray(node.all)) return node.all.every((child) => matches(child as Record<string, unknown>, input));
  if (Array.isArray(node.any)) return node.any.some((child) => matches(child as Record<string, unknown>, input));
  if (node.not) return !matches(node.not as Record<string, unknown>, input);
  const [var_strKey, var_objExpected] = Object.entries(node)[0];
  if (var_strKey === "phase") {
    if (var_objExpected === "any") return true;
    return input.phase === var_objExpected;
  }
  if (var_strKey.startsWith("state.")) {
    return input.unit[var_strKey.slice(6) as keyof UnitSnapshot] === var_objExpected;
  }
  if (var_strKey === "unit_keyword") return (input.unitKeywords ?? []).includes(String(var_objExpected));
  if (var_strKey === "weapon_keyword") {
    return (input.weapons ?? []).some((item) => (item.keywords ?? []).includes(String(var_objExpected)));
  }
  if (var_strKey === "turn_owner") {
    if (var_objExpected === "both") return true;
    return input.game?.turnOwner === var_objExpected;
  }
  if (var_strKey === "is_leading") return Boolean(input.game?.isLeading) === Boolean(var_objExpected);
  if (var_strKey === "game.round") return input.game?.round === var_objExpected;
  if (var_strKey === "game.shadow_of_chaos") {
    const var_lstAreas = input.game?.shadow ?? [];
    const var_lstContested = var_lstAreas.filter((item) => item === "nml" || item === "opp_dz");
    if (var_objExpected === true) return var_lstContested.length > 0;
    if (var_objExpected === false) return var_lstContested.length === 0;
    return var_lstAreas.includes(String(var_objExpected));
  }
  return false;
}

export function evaluateMany(count: number): number {
  const var_fltStarted = performance.now();
  const var_objUnit: UnitSnapshot = {
    moved: "advanced",
    shot: false,
    charged: false,
    fought: false,
    engaged: false,
    on_action: false,
    battle_shocked: false,
    destroyed: false,
  };
  for (let var_intIndex = 0; var_intIndex < count; var_intIndex += 1) {
    evaluateUnit({
      phase: "shooting",
      unit: var_objUnit,
      weapons: [{ name: "Claws", keywords: var_intIndex % 2 ? ["ASSAULT"] : [] }],
    });
  }
  return performance.now() - var_fltStarted;
}
