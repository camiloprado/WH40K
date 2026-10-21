export type WeaponProfile = {
  name: string;
  attacks?: string | null;
  skill?: number | null;
  strength?: number | null;
  ap?: number | null;
  damage?: string | null;
  keywords?: string[];
  /** Número de armas / modelos atacantes com este perfil. */
  count?: number;
};

export type TargetProfile = {
  name: string;
  toughness: number;
  save: number;
  invuln?: number | null;
  wounds: number;
  fnp?: number | null;
  models?: number;
};

export type DamageToggles = {
  sustained?: number;
  lethal?: boolean;
  twinLinked?: boolean;
  torrent?: boolean;
  /** B1: Heavy / "parada" */
  stationary?: boolean;
  /** B1: Charge / "carregou" */
  charged?: boolean;
  /** B1: Half range / "meio alcance" */
  halfRange?: boolean;
};

export function diceAverage(expr: string | null | undefined): number | null {
  const var_lstFaces = damageFaces(expr);
  if (!var_lstFaces) return null;
  return var_lstFaces.reduce((sum, [d, p]) => sum + d * p, 0);
}

/** Faces e probabilidade de uma expressão de dano/ataques. Null se inválida. */
export function damageFaces(expr: string | null | undefined): [number, number][] | null {
  if (expr == null || expr === "") return null;
  const var_strToken = String(expr).toUpperCase().replace(/\s/g, "");
  const var_objDice = var_strToken.match(/^(\d)?D([36])(?:\+(\d{1,2}))?$/);
  if (var_objDice) {
    const var_intCount = Number(var_objDice[1] || 1);
    const var_intFaces = Number(var_objDice[2]);
    const var_intBonus = Number(var_objDice[3] || 0);
    if (var_intCount === 1) {
      const var_fltP = 1 / var_intFaces;
      return Array.from({ length: var_intFaces }, (_, i) => [i + 1 + var_intBonus, var_fltP] as [number, number]);
    }
    let var_lstDist: Map<number, number> = new Map([[0, 1]]);
    for (let n = 0; n < var_intCount; n += 1) {
      const next = new Map<number, number>();
      for (const [total, p] of var_lstDist) {
        for (let face = 1; face <= var_intFaces; face += 1) {
          const key = total + face;
          next.set(key, (next.get(key) || 0) + p / var_intFaces);
        }
      }
      var_lstDist = next;
    }
    return [...var_lstDist.entries()].map(([d, p]) => [d + var_intBonus, p] as [number, number]);
  }
  const var_fltPlain = Number(var_strToken);
  if (!Number.isFinite(var_fltPlain)) return null;
  return [[var_fltPlain, 1]];
}

function binom(n: number, k: number): number {
  if (k < 0 || k > n) return 0;
  let r = 1;
  for (let i = 1; i <= k; i += 1) r = (r * (n - k + i)) / i;
  return r;
}

/** E[min(W, Binomial(d, keep))]. */
export function keptCapped(d: number, wounds: number, keep: number): number {
  if (d <= 0) return 0;
  if (keep >= 1) return Math.min(wounds, d);
  if (keep <= 0) return 0;
  let e = 0;
  for (let k = 0; k <= d; k += 1) {
    e += Math.min(wounds, k) * binom(d, k) * keep ** k * (1 - keep) ** (d - k);
  }
  return e;
}

function woundChance(strength: number, toughness: number): number {
  if (strength >= toughness * 2) return 5 / 6;
  if (strength > toughness) return 4 / 6;
  if (strength === toughness) return 3 / 6;
  if (strength * 2 <= toughness) return 1 / 6;
  return 2 / 6;
}

function sustainedValue(keys: string[], toggles?: DamageToggles): number {
  if (toggles?.sustained != null) return toggles.sustained;
  const sustainedMatch = keys.find((item) => item.startsWith("SUSTAINED"));
  if (!sustainedMatch) return 0;
  const rest = sustainedMatch.replace(/^SUSTAINED(?:\s+HITS)?\s*/i, "").trim();
  if (!rest) return 1;
  const avg = diceAverage(rest);
  if (avg != null) return avg;
  const digits = Number(rest.replace(/[^\d.]/g, ""));
  return Number.isFinite(digits) && digits > 0 ? digits : 1;
}

function keywordFlags(weapon: WeaponProfile, toggles?: DamageToggles) {
  const keys = (weapon.keywords || []).map((item) => item.toUpperCase());
  // Lethal condicional ("contra X") só entra via toggle até existir alvo com keywords (B1).
  const lethalRaw = keys.some((item) => item.includes("LETHAL"));
  const lethalConditional = keys.some(
    (item) => item.includes("LETHAL") && (item.includes("(") || /\b(AGAINST|VS|CONTRA)\b/.test(item)),
  );
  return {
    sustained: sustainedValue(keys, toggles),
    lethal: toggles?.lethal ?? (lethalRaw && !lethalConditional),
    twinLinked: toggles?.twinLinked ?? keys.some((item) => item.includes("TWIN")),
    torrent: toggles?.torrent ?? keys.some((item) => item.includes("TORRENT")),
  };
}

/**
 * Média por ataque com FNP e teto W exatos por face; multiplica pelo count; teto models×W.
 * Keywords: Torrent (auto-hit), Lethal Hits, Sustained Hits N, Twin-linked (rerroll wound).
 * Lethal+Sustained: (h−c)·w + c + c·S·w (B1).
 */
export function expectedDamage(
  weapon: WeaponProfile,
  target: TargetProfile,
  toggles?: DamageToggles,
): number | null {
  const var_lstAttacks = damageFaces(weapon.attacks);
  const var_lstDamage = damageFaces(weapon.damage);
  const flags = keywordFlags(weapon, toggles);
  // M2: sem skill só Torrent (auto-hit) tem número; o resto devolve null.
  if (!var_lstAttacks || !var_lstDamage || weapon.strength == null) return null;
  if (weapon.skill == null && !flags.torrent) return null;
  const var_fltAttacks = var_lstAttacks.reduce((sum, [d, p]) => sum + d * p, 0);
  const var_intSkill = weapon.skill ?? 7;
  let var_fltHit = flags.torrent ? 1 : Math.min(5 / 6, Math.max(0, (7 - var_intSkill) / 6));
  let var_fltWound = woundChance(weapon.strength, target.toughness);
  if (flags.twinLinked) {
    var_fltWound = var_fltWound + (1 - var_fltWound) * var_fltWound;
  }
  const var_fltCrit = flags.torrent ? 0 : 1 / 6;
  const var_fltS = flags.sustained > 0 ? flags.sustained : 0;
  // Por ataque: (h−c)·w + c·[lethal] + c·S·w  (sem lethal, c volta a ferir com w).
  let var_fltWoundPass: number;
  if (flags.lethal) {
    const h = var_fltHit;
    const c = var_fltCrit;
    const w = var_fltWound;
    var_fltWoundPass = (h - c) * w + c + c * var_fltS * w;
  } else {
    var_fltWoundPass = (var_fltHit + var_fltCrit * var_fltS) * var_fltWound;
  }
  const var_intNeeded = target.save - (weapon.ap ?? 0);
  let var_fltSaveFail = var_intNeeded > 6 ? 1 : Math.max(0, 1 - (7 - Math.max(var_intNeeded, 2)) / 6);
  if (target.invuln) {
    const var_fltInvulnFail = 1 - (7 - target.invuln) / 6;
    var_fltSaveFail = Math.min(var_fltSaveFail, var_fltInvulnFail);
  }
  const var_fltKeep = target.fnp ? (target.fnp - 1) / 6 : 1;
  const var_intWounds = Math.max(1, target.wounds || 1);
  const var_fltPerAttack = var_lstDamage.reduce((sum, [d, p]) => sum + p * keptCapped(d, var_intWounds, var_fltKeep), 0);
  const var_intShooters = Math.max(1, weapon.count ?? 1);
  const var_fltRaw = var_intShooters * var_fltAttacks * var_fltWoundPass * var_fltSaveFail * var_fltPerAttack;
  const var_fltCap = (target.models ?? 1) * var_intWounds;
  return Math.min(var_fltRaw, var_fltCap);
}
