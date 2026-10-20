import { expect, test } from "@playwright/test";

test("battle-shock persiste até o próximo passo próprio e some ao passar", async ({ page }) => {
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
        version: { id: 1, faction_name: "Chaos - Chaos Daemons", secondaries: [], created_at: "2026-10-15T12:00:00Z" },
        list: { name: "Daemons", accent_color: "#6E2430" },
        units: [{ id: 1, datasheet_name: "Daemonettes", keywords: [], wargear: [] }],
        abilities: [],
        rule_effects: [],
        attachments: [],
      },
    });
    tx.objectStore("meta").put({ key: "active_bundle", bundleId: 1, schema: 1 });
    tx.objectStore("games").put({
      id: "bs-demo",
      listVersionId: 1,
      bundleEtag: "local",
      opponentName: "Mesa",
      opponentFaction: "",
      missionName: "",
      firstPlayer: "me",
      cpMe: 0,
      cpOpponent: 0,
      seq: 3,
      status: "active",
      updatedAt: Date.now(),
    });
    const put = (seq: number, type: string, payload: Record<string, unknown>, at: string) =>
      tx.objectStore("game_events").put({
        id: `00000000-0000-4000-8000-${String(seq).padStart(12, "0")}`,
        game_id: "bs-demo",
        seq,
        device_id: "e2e",
        type,
        payload,
        created_at: at,
      });
    put(1, "game_started", { first_player: "me", units: [{ list_unit_id: 1, name: "Daemonettes" }] }, "2026-10-15T12:00:00Z");
    put(2, "phase_advanced", {}, "2026-10-15T12:00:01Z");
    put(3, "phase_advanced", {}, "2026-10-15T12:00:02Z");
    put(4, "battleshock_result", { list_unit_id: 1, passed: false }, "2026-10-15T12:00:03Z");
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  });
  await page.goto("/games/bs-demo");
  await expect(page.locator('[data-unit="1"]')).toContainText("Daemonettes");
  for (let step = 0; step < 20; step += 1) {
    const next = page.getByRole("button", { name: /Próxima fase/i });
    if (await page.getByRole("heading", { name: /Battle-shock/i }).isVisible().catch(() => false)) {
      if (await page.getByText(/já em battle-shock/i).isVisible().catch(() => false)) break;
    }
    if (await next.isVisible()) await next.click();
  }
  await expect(page.getByText(/já em battle-shock/i)).toBeVisible();
  await page.getByRole("button", { name: "Passou" }).first().click();
  await expect(page.getByText(/já em battle-shock/i)).toHaveCount(0);
});
