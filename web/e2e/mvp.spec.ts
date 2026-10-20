import { expect, test } from "@playwright/test";

test("daemonettes que avançou fica cinza no tiro", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "wakeLock", { configurable: true, value: undefined });
  });
  await page.goto("/");
  await expect(page.getByRole("link", { name: "List Companion" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Listas" })).toBeVisible();
  await page.evaluate(async () => {
    const open = indexedDB.open("list-companion");
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      open.onsuccess = () => resolve(open.result);
      open.onerror = () => reject(open.error);
    });
    const tx = database.transaction(["bundles", "meta", "games", "game_events"], "readwrite");
    tx.objectStore("bundles").put({
      id: 1,
      savedAt: new Date().toISOString(),
      payload: {
        bundle_schema_version: 1,
        version: { id: 1, secondaries: [], created_at: "2026-10-15T12:00:00Z" },
        list: { name: "Daemons", accent_color: "#6E2430" },
        units: [
          { id: 1, datasheet_id: 50, datasheet_name: "Daemonettes", keywords: [], wargear: [{ weapon_name: "Piercing claws", keywords: [] }] },
          { id: 2, datasheet_name: "Unidade Assault Fixture", keywords: [], wargear: [{ weapon_name: "Arma Curta", keywords: ["ASSAULT"] }] },
        ],
        abilities: [
          { id: 9, kind: "stratagem", name: "Exemplo — gastar 1 CP", cp_cost: 1, use_limit: "per_phase" },
          { id: 10, kind: "unit", datasheet_id: 50, name: "Escolha do herói" },
          { id: 11, kind: "detachment", name: "Vow do detachment" },
        ],
        rule_effects: [
          {
            id: 100,
            ability_id: 10,
            phase: "command",
            turn_owner: "own",
            timing: "start",
            effect_kind: "prompt",
            owner_label: "Herói",
            effect_text: "Escolha dois efeitos",
            unit_ids: [1],
            choice_options: ["Efeito A", "Efeito B", "Efeito C"],
            choice_count: 2,
            choice_scope: "turn",
          },
          {
            id: 101,
            ability_id: 11,
            phase: "command",
            turn_owner: "own",
            timing: "start",
            effect_kind: "prompt",
            owner_label: "Detachment",
            effect_text: "Escolha um vow",
            unit_ids: [],
            choice_options: ["Vow X", "Vow Y"],
            choice_count: 1,
            choice_scope: "battle",
          },
        ],
        attachments: [],
      },
    });
    tx.objectStore("meta").put({ key: "active_bundle", bundleId: 1, schema: 1 });
    tx.objectStore("games").put({
      id: "demo",
      listVersionId: 1,
      bundleEtag: "local",
      opponentName: "Mesa",
      opponentFaction: "",
      missionName: "",
      firstPlayer: "me",
      cpMe: 1,
      cpOpponent: 0,
      seq: 1,
      status: "active",
      updatedAt: Date.now(),
    });
    tx.objectStore("game_events").put({
      id: "11111111-1111-4111-8111-111111111111",
      game_id: "demo",
      seq: 1,
      device_id: "device-a",
      type: "game_started",
      created_at: "2020-01-01T00:00:00Z",
      payload: {
        first_player: "me",
        cp_me: 1,
        units: [
          { list_unit_id: 1, name: "Daemonettes" },
          { list_unit_id: 2, name: "Unidade Assault Fixture" },
        ],
      },
    });
    await new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve(undefined);
      tx.onerror = () => reject(tx.error);
    });
  });
  await page.goto("/games/demo");
  await expect(page.getByText("Tela pode apagar")).toBeVisible();
  const currentPhase = page.locator(".phase-step.on");
  const daemonettes = page.locator('[data-unit="1"]');
  const assault = page.locator('[data-unit="2"]');
  const inspector = page.getByRole("region", { name: "Unidade selecionada" });

  await expect(currentPhase).toHaveText("Início");
  await page.getByRole("button", { name: "Próxima fase" }).click();
  await expect(currentPhase).toHaveText("Command");

  const general = page.getByLabel(/Efeitos gerais/);
  await expect(general).toContainText("Vow do detachment");
  await general.getByRole("button", { name: "Vow Y" }).click();
  await general.getByRole("button", { name: /Confirmar/ }).click();
  await expect(general).toContainText("Escolhido na batalha: Vow Y");

  await expect(daemonettes).toContainText("Escolher: Escolha do herói");
  await daemonettes.click();
  const personal = inspector.getByLabel("Efeitos desta unidade");
  await personal.getByRole("button", { name: "Efeito A" }).click();
  await personal.getByRole("button", { name: "Efeito C" }).click();
  await expect(personal.getByRole("button", { name: "Efeito B" })).toBeDisabled();
  await personal.getByRole("button", { name: /Confirmar/ }).click();
  await expect(daemonettes).toContainText("Efeito A · Efeito C");

  await page.keyboard.press("Escape");
  await daemonettes.dragTo(page.getByRole("region", { name: "Esquerda" }));
  await expect(page.getByRole("region", { name: "Esquerda" }).locator('[data-unit="1"]')).toBeVisible();
  await daemonettes.click();
  await inspector.getByRole("button", { name: "Direita" }).click();
  await expect(page.getByRole("region", { name: "Direita" }).locator('[data-unit="1"]')).toBeVisible();
  await inspector.getByRole("button", { name: "Home", exact: true }).click();
  await expect(page.getByRole("region", { name: "Home" }).locator('[data-unit="1"]')).toBeVisible();

  await page.getByRole("button", { name: "Próxima fase" }).click();
  await expect(currentPhase).toHaveText("Battle-shock");
  await page.keyboard.press("n");
  await expect(currentPhase).toHaveText("Movement");
  await expect(daemonettes).toContainText("Efeito A · Efeito C");
  await expect(general).toContainText("Vow Y");

  await daemonettes.click();
  await inspector.getByRole("button", { name: "Avançou", exact: true }).click();
  await expect(daemonettes).toContainText("Já moveu");
  await assault.click();
  await inspector.getByRole("button", { name: "Avançou", exact: true }).click();
  await expect(assault).toContainText("Já moveu");

  await page.getByRole("button", { name: "Próxima fase" }).click();
  await expect(currentPhase).toHaveText("Shooting");
  await expect(daemonettes).toContainText("Avançou — sem ASSAULT");
  await expect(assault).toContainText("Só armas ASSAULT");
  await expect(daemonettes).toHaveClass(/inactive/);

  await assault.dblclick();
  await expect(assault).toHaveClass(/tapped/);
  await page.keyboard.press("Control+z");
  await expect(assault).not.toHaveClass(/tapped/);

  await page.reload();
  await expect(daemonettes).toContainText("Avançou — sem ASSAULT");

  await daemonettes.dragTo(page.getByRole("region", { name: "Destruídas" }), { targetPosition: { x: 40, y: 12 } });
  await expect(page.getByRole("region", { name: "Destruídas" }).locator('[data-unit="1"]')).toBeVisible();
  await expect(page.getByRole("region", { name: "Mesa" }).locator('[data-unit="1"]')).toHaveCount(0);
});
