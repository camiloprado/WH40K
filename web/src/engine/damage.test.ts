import { describe, expect, it } from "vitest";
import { diceAverage, expectedDamage } from "./damage";

describe("dano esperado", () => {
  it("média de dados", () => {
    expect(diceAverage("D6")).toBe(3.5);
    expect(diceAverage("2D6+1")).toBe(8);
  });

  // BS3+ S4 AP-1 vs T4 Sv3+ → 4/6 × 3/6 × 3/6 = 1/6 por ataque
  const baseWeapon = { name: "Arma", attacks: "2", skill: 3, strength: 4, ap: -1, damage: "1" };
  const baseTarget = { name: "Alvo", toughness: 4, save: 3, wounds: 2, models: 1 };

  it("D1 igual ao legado", () => {
    expect(expectedDamage({ ...baseWeapon, damage: "1" }, baseTarget)).toBe(0.3);
  });

  it("limita dano por ataque ao W", () => {
    expect(expectedDamage({ ...baseWeapon, damage: "3" }, baseTarget)).toBe(0.7);
  });

  it("models do alvo não multiplica o meio", () => {
    expect(expectedDamage({ ...baseWeapon, damage: "3" }, { ...baseTarget, models: 5 })).toBe(0.7);
  });

  it("FNP antes do limite; D6 vs W2 FNP 5+", () => {
    expect(
      expectedDamage({ ...baseWeapon, damage: "D6" }, { ...baseTarget, wounds: 2, fnp: 5, models: 1 }),
    ).toBe(0.7);
  });

  it("multiplica pelo count do atacante", () => {
    expect(
      expectedDamage({ ...baseWeapon, damage: "1", count: 10 }, { name: "Alvo", toughness: 4, save: 3, wounds: 1, models: 10 }),
    ).toBe(3.3);
  });

  it("teto models × W", () => {
    expect(
      expectedDamage(
        { name: "Heavy", attacks: "6", skill: 2, strength: 8, ap: -3, damage: "2", count: 5 },
        { name: "Alvo", toughness: 4, save: 3, wounds: 1, models: 3 },
      ),
    ).toBe(3.0);
  });

  it("invuln no save", () => {
    expect(
      expectedDamage(
        { name: "Melta", attacks: "4", skill: 3, strength: 10, ap: -4, damage: "2" },
        { name: "Alvo", toughness: 5, save: 2, invuln: 4, wounds: 3, models: 1 },
      ),
    ).toBe(2.2);
  });
});
