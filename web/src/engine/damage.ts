export type WeaponProfile = {
  name: string;
  attacks?: string | null;
  skill?: number | null;
  strength?: number | null;
  ap?: number | null;
  damage?: string | null;
  keywords?: string[];
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
  const token = expr.toUpperCase().replace(/\s/g, "");
  const dice = token.match(/^(\d)?D([36])(?:\+(\d{1,2}))?$/);
  if (dice) {
    const count = Number(dice[1] || 1);
    const faces = Number(dice[2]);
    const bonus = Number(dice[3] || 0);
    return count * ((faces + 1) / 2) + bonus;
  }
  const plain = Number(token);
  return Number.isFinite(plain) ? plain : 0;
}

function woundChance(strength: number, toughness: number): number {
  if (strength >= toughness * 2) return 5 / 6;
  if (strength > toughness) return 4 / 6;
  if (strength === toughness) return 3 / 6;
  if (strength * 2 <= toughness) return 1 / 6;
  return 2 / 6;
}

export function expectedDamage(weapon: WeaponProfile, target: TargetProfile): number {
  const attacks = diceAverage(weapon.attacks);
  const damage = diceAverage(weapon.damage);
  const skill = weapon.skill ?? 4;
  const strength = weapon.strength ?? target.toughness;
  const hit = Math.max(0, Math.min(1, (7 - skill) / 6));
  const wound = woundChance(strength, target.toughness);
  const needed = target.save - (weapon.ap ?? 0);
  let saveFail = needed > 6 ? 1 : Math.max(0, 1 - (7 - Math.max(needed, 2)) / 6);
  if (target.invuln) {
    const invulnFail = 1 - (7 - target.invuln) / 6;
    saveFail = Math.min(saveFail, invulnFail);
  }
  const fnpKeep = target.fnp ? 1 - (7 - target.fnp) / 6 : 1;
  const perModel = attacks * hit * wound * saveFail * damage * fnpKeep;
  return Math.round(perModel * (target.models ?? 1) * 10) / 10;
}
