import { describe, expect, it } from "vitest";
import { canStartAction, evaluateMany, evaluateUnit, type UnitSnapshot } from "./eligibility";

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
    expect(evaluateUnit({ phase: "shooting", unit: fell, weapons: [{ name: "Rifle", kind: "ranged" }] }).status).toBe(
      "inactive",
    );
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

  it("engajada não carrega e só atira CLOSE-QUARTERS / PISTOL", () => {
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
        { name: "Rifle", kind: "ranged" },
      ],
    });
    expect(pistol.status).toBe("active");
    expect(pistol.allowedWeapons).toEqual(["Lash"]);
    expect(pistol.reasons.some((item) => item.includes("−1") || item.includes("-1"))).toBe(false);
    const close = evaluateUnit({
      phase: "shooting",
      unit: engaged,
      weapons: [{ name: "Bolt", kind: "ranged", keywords: ["CLOSE-QUARTERS"] }],
    });
    expect(close.status).toBe("active");
    expect(close.allowedWeapons).toEqual(["Bolt"]);
    const blast = evaluateUnit({
      phase: "shooting",
      unit: engaged,
      weapons: [{ name: "Grenade", kind: "ranged", keywords: ["PISTOL", "BLAST"] }],
    });
    expect(blast.status).toBe("inactive");
  });

  it("MONSTER/VEHICLE engajado mantém armas e avisa −1 e BLAST", () => {
    const result = evaluateUnit({
      phase: "shooting",
      unit: base({ engaged: true }),
      unitKeywords: ["VEHICLE"],
      weapons: [
        { name: "Cannon", kind: "ranged", keywords: ["BLAST"] },
        { name: "Gun", kind: "ranged" },
        { name: "Flamer", kind: "ranged", keywords: ["CLOSE-QUARTERS"] },
      ],
    });
    expect(result.status).toBe("active");
    expect(result.allowedWeapons).toEqual(["Cannon", "Gun", "Flamer"]);
    expect(result.reasons.some((item) => item.includes("−1"))).toBe(true);
    expect(result.reasons.some((item) => item.includes("BLAST"))).toBe(true);
  });

  it("engajada e avançou não atira", () => {
    const result = evaluateUnit({
      phase: "shooting",
      unit: base({ engaged: true, moved: "advanced" }),
      weapons: [
        { name: "Lash", kind: "ranged", keywords: ["PISTOL"] },
        { name: "Claws", kind: "ranged", keywords: ["ASSAULT"] },
      ],
    });
    expect(result.status).toBe("inactive");
    expect(result.allowedWeapons).toEqual([]);
    expect(result.reasons).toContain("Engajada e avançou — sem tiro");
    const freed = evaluateUnit({
      phase: "shooting",
      unit: base({ engaged: true, moved: "advanced", overrides: [{ key: "shoot_engaged" }] }),
      weapons: [{ name: "Lash", kind: "ranged", keywords: ["PISTOL"] }],
    });
    expect(freed.status).not.toBe("inactive");
  });

  it("unidade sem arma de tiro já conta como tendo atirado", () => {
    const onlyMelee = evaluateUnit({ phase: "shooting", unit: base(), weapons: [{ name: "Espada", kind: "melee" }] });
    expect(onlyMelee.status).toBe("done");
    expect(onlyMelee.reasons).toContain("Sem arma de tiro");
    const empty = evaluateUnit({ phase: "shooting", unit: base(), weapons: [] });
    expect(empty.status).toBe("done");
  });

  it("canStartAction bloqueia engajada e libera TITANIC", () => {
    expect(canStartAction(base({ engaged: true }))).toContain("Engajada: não começa ação");
    expect(canStartAction(base({ engaged: true }), ["TITANIC"]).some((item) => item.includes("Engajada"))).toBe(false);
    expect(canStartAction(base({ battle_shocked: true }))).toContain("Em battle-shock: não começa ação");
  });

  it("fato desconhecido falha fechado e turn_owner discrimina", () => {
    const allowOpp = {
      effect_kind: "allow",
      restriction_key: "shoot_after_advance",
      condition_json: { turn_owner: "opponent" },
    };
    const mine = evaluateUnit({
      phase: "shooting",
      unit: base({ moved: "advanced" }),
      weapons: [{ name: "Rifle", kind: "ranged" }],
      effects: [allowOpp],
      game: { turnOwner: "own" },
    });
    expect(mine.status).toBe("inactive");
    const opp = evaluateUnit({
      phase: "shooting",
      unit: base({ moved: "advanced" }),
      weapons: [{ name: "Rifle", kind: "ranged" }],
      effects: [allowOpp],
      game: { turnOwner: "opponent" },
    });
    expect(opp.status).toBe("active");
  });

  it("C11 turno do oponente inativa MOV/SHT/CHG salvo overwatch", () => {
    for (const phase of ["movement", "shooting", "charge"] as const) {
      const blocked = evaluateUnit({
        phase,
        unit: base({ engaged: phase === "charge" ? false : true }),
        weapons: [{ name: "Rifle", kind: "ranged" }],
        activePlayer: "opponent",
      });
      expect(blocked.status).toBe("inactive");
      expect(blocked.reasons).toContain("Turno do oponente");
    }
    const overwatch = evaluateUnit({
      phase: "shooting",
      unit: base({ overrides: [{ key: "overwatch" }] }),
      weapons: [{ name: "Rifle", kind: "ranged" }],
      activePlayer: "opponent",
    });
    expect(overwatch.status).not.toBe("inactive");
    expect(
      evaluateUnit({
        phase: "fight",
        unit: base({ engaged: true }),
        activePlayer: "opponent",
      }).status,
    ).toBe("active");
  });

  it("C16 engajada na Movement avisa fica parada ou recua", () => {
    const engaged = evaluateUnit({ phase: "movement", unit: base({ engaged: true }) });
    expect(engaged.reasons).toContain("Engajada: fica parada ou recua");
    expect(evaluateUnit({ phase: "movement", unit: base() }).reasons).not.toContain("Engajada: fica parada ou recua");
  });

  it("Desperate Escape quando engajada e em battle-shock na Movement", () => {
    const result = evaluateUnit({
      phase: "movement",
      unit: base({ engaged: true, battle_shocked: true }),
    });
    expect(result.status).toBe("warn");
    expect(result.reasons.some((item) => item.includes("Desperate Escape"))).toBe(true);
    expect(
      evaluateUnit({ phase: "movement", unit: base({ engaged: true }) }).reasons.some((item) =>
        item.includes("Desperate Escape"),
      ),
    ).toBe(false);
    expect(
      evaluateUnit({ phase: "movement", unit: base({ battle_shocked: true }) }).reasons.some((item) =>
        item.includes("Desperate Escape"),
      ),
    ).toBe(false);
  });

  it("Overrun fight quando carregou ou estava engajada no começo", () => {
    const charged = evaluateUnit({ phase: "fight", unit: base({ charged: true }) });
    expect(charged.status).toBe("active");
    expect(charged.reasons.some((item) => item.includes("Overrun"))).toBe(true);
    const was = evaluateUnit({
      phase: "fight",
      unit: base({ engaged_at_fight_start: true }),
    });
    expect(was.status).toBe("active");
    expect(was.reasons.some((item) => item.includes("Overrun"))).toBe(true);
    expect(evaluateUnit({ phase: "fight", unit: base() }).status).toBe("inactive");
  });

  it("avisos: avançou não começa ação e escolha CQ", () => {
    const advanced = evaluateUnit({
      phase: "shooting",
      unit: base({ moved: "advanced" }),
      weapons: [{ name: "Claws", kind: "ranged", keywords: ["ASSAULT"] }],
    });
    expect(advanced.reasons).toContain("Avançou: não começa ação neste turno");
    const choice = evaluateUnit({
      phase: "shooting",
      unit: base(),
      weapons: [
        { name: "Rifle", kind: "ranged" },
        { name: "Pistol", kind: "ranged", keywords: ["PISTOL"] },
      ],
    });
    expect(choice.reasons).toContain("Escolha: CLOSE-QUARTERS ou as outras armas");
  });

  it("trinta unidades ficam abaixo de 20 ms", () => {
    expect(evaluateMany(30)).toBeLessThan(20);
  });
});
