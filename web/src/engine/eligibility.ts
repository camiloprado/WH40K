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

const DONE: Record<string, { flag: keyof UnitSnapshot; label: string }> = {
  movement: { flag: "moved", label: "Já moveu" },
  shooting: { flag: "shot", label: "Já atirou" },
  charge: { flag: "charged", label: "Já carregou" },
  fight: { flag: "fought", label: "Já lutou" },
};

export function evaluateUnit(input: {
  phase: string;
  unit: UnitSnapshot;
  weapons?: WeaponRef[];
  unitKeywords?: string[];
  effects?: RuleEffect[];
}): Eligibility {
  const weapons = input.weapons ?? [];
  const names = weapons.map((item) => item.name);
  const overrides = new Set((input.unit.overrides ?? []).map((item) => item.key));
  const allows = new Set<string>();
  const denies = new Set<string>();
  const weaponFilters: string[] = [];
  for (const effect of input.effects ?? []) {
    if (!matches(effect.condition_json ?? {}, input)) continue;
    if (!effect.restriction_key) continue;
    if (effect.effect_kind === "allow") {
      allows.add(effect.restriction_key);
      const filter = keywordFilter(effect.condition_json);
      if (filter) weaponFilters.push(filter);
    }
    if (effect.effect_kind === "deny") denies.add(effect.restriction_key);
  }
  const permitted = (key: string) => (allows.has(key) || overrides.has(key)) && !denies.has(key);
  if (input.unit.destroyed || denies.has("destroyed")) {
    return { status: "inactive", reasons: ["Destruída"], allowedWeapons: [], destroyed: true };
  }
  if (input.phase === "shooting" && !hasRanged(weapons)) {
    return { status: "done", reasons: ["Sem arma de tiro"], allowedWeapons: [], destroyed: false };
  }
  const doneEarly = phaseDone(input.phase, input.unit);
  if (doneEarly) {
    return { status: "done", reasons: [doneEarly], allowedWeapons: names, destroyed: false };
  }
  const reasons: string[] = [];
  let allowed = names;
  let inactive = false;
  if (input.phase === "shooting") {
    if (input.unit.moved === "advanced" && !permitted("shoot_after_advance")) {
      const assault = weapons.filter((item) => keywordsOf(item).includes("ASSAULT")).map((item) => item.name);
      if (assault.length === 0) {
        inactive = true;
        reasons.push("Avançou — sem ASSAULT");
        allowed = [];
      } else {
        allowed = assault;
        reasons.push("Só armas ASSAULT");
      }
    } else if (input.unit.moved === "advanced" && permitted("shoot_after_advance")) {
      reasons.push("Permitido por regra");
      if (weaponFilters.length) {
        allowed = weapons.filter((item) => weaponFilters.every((key) => (item.keywords ?? []).includes(key))).map((item) => item.name);
        if (allowed.length === 0) {
          inactive = true;
          reasons.push("Avançou — sem ASSAULT");
        }
      }
    }
    if (input.unit.moved === "fell_back" && !permitted("shoot_after_fall_back")) {
      inactive = true;
      reasons.push("Recuou");
      allowed = [];
    } else if (input.unit.moved === "fell_back") reasons.push("Permitido por regra");
    if (input.unit.on_action && !permitted("shoot_on_action")) {
      inactive = true;
      reasons.push("Em ação");
      allowed = [];
    }
    const monster = (input.unitKeywords ?? []).some((item) => item.toUpperCase() === "MONSTER" || item.toUpperCase() === "VEHICLE");
    if (input.unit.engaged && !monster && !permitted("shoot_engaged")) {
      const pistols = weapons.filter((item) => keywordsOf(item).includes("PISTOL")).map((item) => item.name);
      if (pistols.length === 0) {
        inactive = true;
        reasons.push("Em combate");
        allowed = [];
      } else {
        allowed = pistols;
        reasons.push("Só armas PISTOL");
      }
    }
  }
  if (input.phase === "charge") {
    if (input.unit.engaged) {
      inactive = true;
      reasons.push("Já está em combate");
    }
    if ((input.unit.moved === "advanced" && !permitted("charge_after_advance")) || (input.unit.moved === "fell_back" && !permitted("charge_after_fall_back"))) {
      inactive = true;
      reasons.push(input.unit.moved === "advanced" ? "Avançou" : "Recuou");
    } else if (input.unit.moved === "advanced" || input.unit.moved === "fell_back") reasons.push("Permitido por regra");
    if (input.unit.on_action) {
      inactive = true;
      reasons.push("Em ação");
    }
  }
  if (input.phase === "fight" && !input.unit.engaged && !input.unit.charged && !permitted("fight_again")) {
    inactive = true;
    reasons.push("Não está em combate");
  }
  if (input.unit.battle_shocked) reasons.push("Battle-shock: OC vira traço, não pode ser alvo de stratagem nem começar ou concluir ação");
  const done = phaseDone(input.phase, input.unit);
  if (done && !inactive) {
    return { status: "done", reasons: [done, ...reasons], allowedWeapons: allowed, destroyed: false };
  }
  if (inactive) return { status: "inactive", reasons, allowedWeapons: allowed, destroyed: false };
  if (input.unit.battle_shocked && input.phase !== "battle_shock") {
    return { status: "warn", reasons, allowedWeapons: allowed, destroyed: false };
  }
  return { status: "active", reasons, allowedWeapons: allowed, destroyed: false };
}

function keywordsOf(weapon: WeaponRef): string[] {
  return (weapon.keywords ?? []).map((item) => item.toUpperCase());
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
  for (const key of ["all", "any"] as const) {
    const children = node[key];
    if (Array.isArray(children)) {
      for (const child of children) {
        const found = keywordFilter(child as Record<string, unknown>);
        if (found) return found;
      }
    }
  }
  return null;
}

function matches(node: Record<string, unknown>, input: { phase: string; unit: UnitSnapshot; weapons?: WeaponRef[]; unitKeywords?: string[] }): boolean {
  if (!node || Object.keys(node).length === 0) return true;
  if (Array.isArray(node.all)) return node.all.every((child) => matches(child as Record<string, unknown>, input));
  if (Array.isArray(node.any)) return node.any.some((child) => matches(child as Record<string, unknown>, input));
  if (node.not) return !matches(node.not as Record<string, unknown>, input);
  const [key, expected] = Object.entries(node)[0];
  if (key === "phase") return input.phase === expected;
  if (key.startsWith("state.")) return input.unit[key.slice(6) as keyof UnitSnapshot] === expected;
  if (key === "unit_keyword") return (input.unitKeywords ?? []).includes(String(expected));
  if (key === "weapon_keyword") return (input.weapons ?? []).some((item) => (item.keywords ?? []).includes(String(expected)));
  return true;
}

export function evaluateMany(count: number): number {
  const started = performance.now();
  const unit: UnitSnapshot = {
    moved: "advanced",
    shot: false,
    charged: false,
    fought: false,
    engaged: false,
    on_action: false,
    battle_shocked: false,
    destroyed: false,
  };
  for (let index = 0; index < count; index += 1) {
    evaluateUnit({ phase: "shooting", unit, weapons: [{ name: "Claws", keywords: index % 2 ? ["ASSAULT"] : [] }] });
  }
  return performance.now() - started;
}
