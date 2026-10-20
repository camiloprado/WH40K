import { expect, it } from "vitest";
import { diceAverage, expectedDamage } from "./damage";

it("média de dados e dano aproximado", () => {
  expect(diceAverage("D6")).toBe(3.5);
  expect(diceAverage("2D6+1")).toBe(8);
  const value = expectedDamage(
    { name: "Arma", attacks: "2", skill: 3, strength: 4, ap: -1, damage: "1" },
    { name: "Alvo", toughness: 4, save: 3, wounds: 2, models: 1 },
  );
  expect(value).toBeGreaterThan(0);
  expect(value).toBeLessThan(2);
});
