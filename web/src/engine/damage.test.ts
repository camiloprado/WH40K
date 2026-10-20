import { describe, expect, it } from "vitest";
import { diceAverage, expectedDamage, keptCapped } from "./damage";

describe("dano esperado", () => {
  it("média de dados", () => {
    expect(diceAverage("D6")).toBe(3.5);
    expect(diceAverage("2D6+1")).toBe(8);
  });

  it("keptCapped exato", () => {
    expect(keptCapped(3, 2, 1)).toBe(2);
    // Face D=3, W=2, keep 4/6 (FNP 5+) — Correcoes ≈ 1,7037
    expect(keptCapped(3, 2, 4 / 6)).toBeCloseTo(1.7037, 3);
  });

  // BS3+ S4 AP-1 vs T4 Sv3+ → 4/6 × 3/6 × 3/6 = 1/6 por ataque
  const baseWeapon = { name: "Arma", attacks: "2", skill: 3, strength: 4, ap: -1, damage: "1" };
  const baseTarget = { name: "Alvo", toughness: 4, save: 3, wounds: 2, models: 1 };

  it("D1 igual ao legado arredondado na UI", () => {
    expect(expectedDamage({ ...baseWeapon, damage: "1" }, baseTarget)).toBeCloseTo(1 / 3, 5);
  });

  it("D3 fixo vs W2", () => {
    expect(expectedDamage({ ...baseWeapon, damage: "3" }, baseTarget)).toBeCloseTo(2 / 3, 5);
  });

  it("models do alvo não multiplica o meio", () => {
    expect(expectedDamage({ ...baseWeapon, damage: "3" }, { ...baseTarget, models: 5 })).toBeCloseTo(2 / 3, 5);
  });

  it("FNP exato; D6 vs W2 FNP 5+", () => {
    const raw = expectedDamage({ ...baseWeapon, damage: "D6" }, { ...baseTarget, wounds: 2, fnp: 5, models: 1 });
    expect(raw).toBeCloseTo(0.5285, 3);
  });

  it("multiplica pelo count do atacante", () => {
    expect(
      expectedDamage({ ...baseWeapon, damage: "1", count: 10 }, { name: "Alvo", toughness: 4, save: 3, wounds: 1, models: 10 }),
    ).toBeCloseTo(10 / 3, 5);
  });

  it("teto models × W", () => {
    expect(
      expectedDamage(
        { name: "Heavy", attacks: "6", skill: 2, strength: 8, ap: -3, damage: "2", count: 5 },
        { name: "Alvo", toughness: 4, save: 3, wounds: 1, models: 3 },
      ),
    ).toBe(3);
  });

  it("invuln no save", () => {
    expect(
      expectedDamage(
        { name: "Melta", attacks: "4", skill: 3, strength: 10, ap: -4, damage: "2" },
        { name: "Alvo", toughness: 5, save: 2, invuln: 4, wounds: 3, models: 1 },
      ),
    ).toBeCloseTo(20 / 9, 5);
  });

  it("perfil incompleto devolve null", () => {
    expect(expectedDamage({ ...baseWeapon, attacks: null }, baseTarget)).toBeNull();
    expect(expectedDamage({ ...baseWeapon, damage: "X" }, baseTarget)).toBeNull();
    expect(expectedDamage({ ...baseWeapon, strength: null }, baseTarget)).toBeNull();
  });

  it("acerto limitado a 5/6", () => {
    const raw = expectedDamage({ ...baseWeapon, skill: 1, damage: "1" }, baseTarget);
    // 2 × 5/6 × 3/6 × 3/6 × 1 = 2 × 5/6 × 1/4 = 10/24
    expect(raw).toBeCloseTo(10 / 24, 5);
  });

  it("B1 Torrent auto-hit aumenta o dano médio", () => {
    const base = expectedDamage({ ...baseWeapon, skill: 4, damage: "1" }, baseTarget)!;
    const torrent = expectedDamage({ ...baseWeapon, skill: 4, damage: "1", keywords: ["TORRENT"] }, baseTarget)!;
    expect(torrent).toBeGreaterThan(base);
  });
});
