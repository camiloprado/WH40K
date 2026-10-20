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
};

export function diceAverage(expr: string | null | undefined): number {
  const var_lstFaces = damageFaces(expr);
  if (!var_lstFaces) return 0;
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

function keywordFlags(weapon: WeaponProfile, toggles?: DamageToggles) {
  const keys = (weapon.keywords || []).map((item) => item.toUpperCase());
  const sustainedMatch = keys.find((item) => item.startsWith("SUSTAINED"));
  const sustainedFromKw = sustainedMatch ? Number(sustainedMatch.replace(/[^\d]/g, "") || 1) : 0;
  return {
    sustained: toggles?.sustained ?? sustainedFromKw,
    lethal: toggles?.lethal ?? keys.some((item) => item.includes("LETHAL")),
    twinLinked: toggles?.twinLinked ?? keys.some((item) => item.includes("TWIN")),
    torrent: toggles?.torrent ?? keys.some((item) => item.includes("TORRENT")),
  };
}

/**
 * Média por ataque com FNP e teto W exatos por face; multiplica pelo count; teto models×W.
 * Keywords: Torrent (auto-hit), Lethal Hits, Sustained Hits N, Twin-linked (rerroll wound).
 */
export function expectedDamage(
  weapon: WeaponProfile,
  target: TargetProfile,
  toggles?: DamageToggles,
): number | null {
  const var_lstAttacks = damageFaces(weapon.attacks);
  const var_lstDamage = damageFaces(weapon.damage);
  if (!var_lstAttacks || !var_lstDamage || weapon.strength == null) return null;
  const flags = keywordFlags(weapon, toggles);
  const var_fltAttacks = var_lstAttacks.reduce((sum, [d, p]) => sum + d * p, 0);
  const var_intSkill = weapon.skill ?? 4;
  let var_fltHit = flags.torrent ? 1 : Math.min(5 / 6, Math.max(0, (7 - var_intSkill) / 6));
  let var_fltWound = woundChance(weapon.strength, target.toughness);
  if (flags.twinLinked) {
    var_fltWound = var_fltWound + (1 - var_fltWound) * var_fltWound;
  }
  // Lethal: hits críticos (6) viram feridas automáticas — aproxima fracção 1/6 dos hits.
  const var_fltCrit = flags.torrent ? 0 : 1 / 6;
  const var_fltNormalHit = Math.max(0, var_fltHit - (flags.lethal ? var_fltCrit : 0));
  const var_fltAutoWound = flags.lethal ? var_fltCrit : 0;
  // Sustained: cada hit crítico gera +N hits extras (média).
  const var_fltExtraHits = flags.sustained > 0 ? var_fltCrit * flags.sustained : 0;
  const var_fltHitEff = var_fltHit + var_fltExtraHits;
  const var_fltWoundPass =
    flags.lethal
      ? (var_fltNormalHit / Math.max(var_fltHit, 1e-9)) * var_fltWound * var_fltHitEff +
        var_fltAutoWound * (var_fltHitEff / Math.max(var_fltHit, 1e-9))
      : var_fltHitEff * var_fltWound;
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
