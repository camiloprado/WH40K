import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

test("recarregar mantém o toggle de regras de evento", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "wakeLock", { configurable: true, value: undefined });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Listas" })).toBeVisible();
  await page.evaluate(async () => {
    const open = indexedDB.open("list-companion");
    const database = await new Promise<IDBDatabase>((resolveDb, reject) => {
      open.onsuccess = () => resolveDb(open.result);
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
        units: [{ id: 1, datasheet_name: "Daemonettes", keywords: [], wargear: [] }],
        abilities: [],
        rule_effects: [],
        attachments: [],
      },
    });
    tx.objectStore("meta").put({ key: "active_bundle", bundleId: 1, schema: 1 });
    tx.objectStore("games").put({
      id: "rules-toggle",
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
      id: "evt-1",
      game_id: "rules-toggle",
      seq: 1,
      device_id: "e2e",
      type: "game_started",
      created_at: "2026-10-15T12:00:00Z",
      payload: {
        first_player: "me",
        phases_v: 2,
        event_rules: false,
        units: [{ list_unit_id: 1, name: "Daemonettes" }],
      },
    });
    await new Promise<void>((resolveTx, reject) => {
      tx.oncomplete = () => resolveTx();
      tx.onerror = () => reject(tx.error);
    });
  });
  await page.goto("/games/rules-toggle");
  // round_start → command
  await page.getByRole("button", { name: /próxima fase/i }).click();
  const toggle = page.getByRole("checkbox", { name: /regras de evento/i });
  await expect(toggle).toBeVisible();
  await expect(toggle).not.toBeChecked();
  await toggle.click();
  await expect(toggle).toBeChecked();
  await page.reload();
  await expect(page.getByRole("checkbox", { name: /regras de evento/i })).toBeChecked();
});

test("login por cookie no proxy (DEV1/SEC-N5)", async ({ page }) => {
  const here = dirname(fileURLToPath(import.meta.url));
  let token = process.env.E2E_TOKEN || "";
  try {
    token = readFileSync(resolve(here, "../.e2e-token"), "utf8").trim() || token;
  } catch {
    token = token;
  }
  if (!token && process.env.CI) throw new Error("CI sem token e2e");
  test.skip(!token, "sem token e2e (API local)");
  await page.goto("/login");
  await page.getByLabel("Token").fill(token);
  await page.getByRole("button", { name: /entrar/i }).click();
  await expect(page.getByRole("heading", { name: "Listas" })).toBeVisible({ timeout: 15_000 });
  const cookies = await page.context().cookies();
  expect(cookies.some((item) => item.name === "session")).toBeTruthy();
});
