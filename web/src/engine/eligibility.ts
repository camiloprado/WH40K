export type Moved = "none" | "normal" | "advanced" | "fell_back" | "remained";

export type UnitSnapshot = {
  moved: Moved;
  shot: boolean;
  charged: boolean;
  fought: boolean;
  engaged: boolean;
  on_action: boolean;
  battle_shocked: boolean;
  destroyed: boolean;
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

export type GameFacts = { round?: number; shadow?: string[] };

export function evaluateUnit(input: {
  phase: string;
  unit: UnitSnapshot;
  weapons?: WeaponRef[];
  unitKeywords?: string[];
  effects?: RuleEffect[];
  game?: GameFacts;
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
  if (input.phase === "shooting" && !hasRanged(var_lstWeapons)) {
    return { status: "done", reasons: ["Sem arma de tiro"], allowedWeapons: [], destroyed: false };
  }
  const var_strDoneEarly = phaseDone(input.phase, input.unit);
  if (var_strDoneEarly) {
    return { status: "done", reasons: [var_strDoneEarly], allowedWeapons: var_lstNames, destroyed: false };
  }
  const var_lstReasons: string[] = [];
  let var_lstAllowed = var_lstNames;
  let var_boolInactive = false;
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
    if (input.unit.on_action && !var_fnPermitted("shoot_on_action")) {
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
  if (input.phase === "fight" && !input.unit.engaged && !input.unit.charged && !var_fnPermitted("fight_again")) {
    var_boolInactive = true;
    var_lstReasons.push("Não está em combate");
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
  if (var_strKey === "phase") return input.phase === var_objExpected;
  if (var_strKey.startsWith("state.")) return input.unit[var_strKey.slice(6) as keyof UnitSnapshot] === var_objExpected;
  if (var_strKey === "unit_keyword") return (input.unitKeywords ?? []).includes(String(var_objExpected));
  if (var_strKey === "weapon_keyword") {
    return (input.weapons ?? []).some((item) => (item.keywords ?? []).includes(String(var_objExpected)));
  }
  if (var_strKey === "game.round") return input.game?.round === var_objExpected;
  if (var_strKey === "game.shadow_of_chaos") {
    const var_lstAreas = input.game?.shadow ?? [];
    if (var_objExpected === true) return var_lstAreas.length > 0;
    if (var_objExpected === false) return var_lstAreas.length === 0;
    return var_lstAreas.includes(String(var_objExpected));
  }
  if (var_strKey.startsWith("game.")) return false;
  return true;
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
