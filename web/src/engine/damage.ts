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

export function diceAverage(expr: string | null | undefined): number {
  if (!expr) return 0;
  const var_strToken = expr.toUpperCase().replace(/\s/g, "");
  const var_objDice = var_strToken.match(/^(\d)?D([36])(?:\+(\d{1,2}))?$/);
  if (var_objDice) {
    const var_intCount = Number(var_objDice[1] || 1);
    const var_intFaces = Number(var_objDice[2]);
    const var_intBonus = Number(var_objDice[3] || 0);
    return var_intCount * ((var_intFaces + 1) / 2) + var_intBonus;
  }
  const var_fltPlain = Number(var_strToken);
  return Number.isFinite(var_fltPlain) ? var_fltPlain : 0;
}

function woundChance(strength: number, toughness: number): number {
  if (strength >= toughness * 2) return 5 / 6;
  if (strength > toughness) return 4 / 6;
  if (strength === toughness) return 3 / 6;
  if (strength * 2 <= toughness) return 1 / 6;
  return 2 / 6;
}

/**
 * Média aproximada: FNP antes do limite por W do modelo; multiplica pelo count do atacante;
 * teto models×W. min(média do dano, W) superestima um pouco vs E[min(W, …)].
 */
export function expectedDamage(weapon: WeaponProfile, target: TargetProfile): number {
  const var_fltAttacks = diceAverage(weapon.attacks);
  const var_fltDamage = diceAverage(weapon.damage);
  const var_intSkill = weapon.skill ?? 4;
  const var_intStrength = weapon.strength ?? target.toughness;
  const var_fltHit = Math.max(0, Math.min(1, (7 - var_intSkill) / 6));
  const var_fltWound = woundChance(var_intStrength, target.toughness);
  const var_intNeeded = target.save - (weapon.ap ?? 0);
  let var_fltSaveFail = var_intNeeded > 6 ? 1 : Math.max(0, 1 - (7 - Math.max(var_intNeeded, 2)) / 6);
  if (target.invuln) {
    const var_fltInvulnFail = 1 - (7 - target.invuln) / 6;
    var_fltSaveFail = Math.min(var_fltSaveFail, var_fltInvulnFail);
  }
  const var_fltFnpKeep = target.fnp ? 1 - (7 - target.fnp) / 6 : 1;
  const var_intWounds = Math.max(1, target.wounds || 1);
  const var_fltPerAttack = Math.min(var_fltDamage * var_fltFnpKeep, var_intWounds);
  const var_intShooters = Math.max(1, weapon.count ?? 1);
  const var_fltRaw = var_intShooters * var_fltAttacks * var_fltHit * var_fltWound * var_fltSaveFail * var_fltPerAttack;
  const var_fltCap = (target.models ?? 1) * var_intWounds;
  return Math.round(Math.min(var_fltRaw, var_fltCap) * 10) / 10;
}
