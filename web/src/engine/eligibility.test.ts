import { describe, expect, it } from "vitest";
import { evaluateMany, evaluateUnit, type UnitSnapshot } from "./eligibility";

const base = (patch: Partial<UnitSnapshot> = {}): UnitSnapshot => ({
  moved: "none",
  shot: false,
  charged: false,
  fought: false,
  engaged: false,
  on_action: false,
  battle_shocked: false,
  destroyed: false,
  ...patch,
});

describe("elegibilidade", () => {
  it("avançou sem ASSAULT fica inativa no tiro", () => {
    const result = evaluateUnit({
      phase: "shooting",
      unit: base({ moved: "advanced" }),
      weapons: [{ name: "Claws", keywords: [] }],
    });
    expect(result.status).toBe("inactive");
    expect(result.reasons).toContain("Avançou — sem ASSAULT");
  });

  it("avançou com ASSAULT libera só essa arma", () => {
    const result = evaluateUnit({
      phase: "shooting",
      unit: base({ moved: "advanced" }),
      weapons: [
        { name: "Claws", keywords: [] },
        { name: "Arma Curta", keywords: ["ASSAULT"] },
      ],
    });
    expect(result.status).toBe("active");
    expect(result.allowedWeapons).toEqual(["Arma Curta"]);
    expect(result.reasons).toContain("Só armas ASSAULT");
  });

  it("recuo bloqueia tiro e carga, allow libera", () => {
    const fell = base({ moved: "fell_back" });
    expect(evaluateUnit({ phase: "shooting", unit: fell, weapons: [{ name: "Rifle", kind: "ranged" }] }).status).toBe("inactive");
    expect(evaluateUnit({ phase: "charge", unit: fell }).status).toBe("inactive");
    const allowed = evaluateUnit({
      phase: "shooting",
      unit: fell,
      weapons: [{ name: "Rifle", kind: "ranged" }],
      effects: [{ effect_kind: "allow", restriction_key: "shoot_after_fall_back", ability_name: "X" }],
    });
    expect(allowed.status).toBe("active");
    expect(allowed.reasons).toContain("Permitido por regra");
  });

  it("luta só engajada ou quem carregou", () => {
    expect(evaluateUnit({ phase: "fight", unit: base() }).status).toBe("inactive");
    expect(evaluateUnit({ phase: "fight", unit: base({ charged: true }) }).status).toBe("active");
    expect(evaluateUnit({ phase: "fight", unit: base({ engaged: true }) }).status).toBe("active");
  });

  it("destruída e override", () => {
    expect(evaluateUnit({ phase: "shooting", unit: base({ destroyed: true }) }).destroyed).toBe(true);
    const overridden = evaluateUnit({
      phase: "charge",
      unit: base({ moved: "advanced", overrides: [{ key: "charge_after_advance" }] }),
    });
    expect(overridden.status).toBe("active");
  });

  it("engajada não carrega e só atira de pistol", () => {
    const engaged = base({ engaged: true });
    expect(evaluateUnit({ phase: "charge", unit: engaged }).status).toBe("inactive");
    expect(evaluateUnit({ phase: "charge", unit: engaged }).reasons).toContain("Já está em combate");
    const melee = evaluateUnit({ phase: "shooting", unit: engaged, weapons: [{ name: "Garras", kind: "melee" }] });
    expect(melee.status).toBe("done");
    expect(melee.reasons).toContain("Sem arma de tiro");
    const pistol = evaluateUnit({
      phase: "shooting",
      unit: engaged,
      weapons: [
        { name: "Garras", kind: "melee" },
        { name: "Lash", kind: "ranged", keywords: ["pistol"] },
      ],
    });
    expect(pistol.status).toBe("active");
    expect(pistol.allowedWeapons).toEqual(["Lash"]);
  });

  it("unidade sem arma de tiro já conta como tendo atirado", () => {
    const onlyMelee = evaluateUnit({ phase: "shooting", unit: base(), weapons: [{ name: "Espada", kind: "melee" }] });
    expect(onlyMelee.status).toBe("done");
    expect(onlyMelee.reasons).toContain("Sem arma de tiro");
    const empty = evaluateUnit({ phase: "shooting", unit: base(), weapons: [] });
    expect(empty.status).toBe("done");
  });

  it("trinta unidades ficam abaixo de 20 ms", () => {
    expect(evaluateMany(30)).toBeLessThan(20);
  });
});
