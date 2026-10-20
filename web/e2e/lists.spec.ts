import { expect, test } from "@playwright/test";

test("a aba Listas nomeia facção, jogo, pontos e partida", async ({ page }) => {
  const rows = [
    {
      id: 1,
      name: "O Banquete Podre",
      current_version: {
        id: 3,
        version_no: 1,
        faction_name: "Chaos - Chaos Daemons",
        battle_size: "Strike Force",
        total_points_declared: 1975,
        points_limit: 2000,
      },
    },
    {
      id: 2,
      name: "Teste Lion",
      current_version: {
        id: 4,
        version_no: 1,
        faction_name: "Imperium - Dark Angels",
        battle_size: "Incursion",
        total_points_declared: 1000,
        points_limit: 1000,
      },
    },
  ];
  await page.route("**/api/v1/games", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/v1/lists", (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(rows) });
  });
  await page.route("**/api/v1/lists/2", (route) => {
    expect(route.request().postDataJSON()).toMatchObject({ confirm: "EXCLUIR" });
    rows.splice(1, 1);
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
  });
  await page.goto("/");
  const army = page.getByRole("region", { name: "Exércitos importados" });
  const card = army.getByRole("link", { name: /O Banquete Podre/ });
  await expect(card).toBeVisible();
  await page.evaluate(async () => {
    const open = indexedDB.open("list-companion");
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      open.onsuccess = () => resolve(open.result);
      open.onerror = () => reject(open.error);
    });
    const tx = database.transaction("games", "readwrite");
    tx.objectStore("games").put({
      id: "demo",
      opponentName: "Mesa",
      missionName: "Take and Hold",
      status: "active",
      updatedAt: Date.now(),
    });
    await new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve(undefined);
      tx.onerror = () => reject(tx.error);
    });
  });
  await page.reload();
  await expect(card).toHaveAccessibleName(/Lista O Banquete Podre Facção Chaos - Chaos Daemons Jogo Strike Force Pontos 1975 \/ 2000 pts Versão v1/);
  const games = page.getByRole("region", { name: "Partidas abertas" });
  await expect(games.getByRole("link", { name: /Partida Contra Mesa Missão Take and Hold/ })).toBeVisible();
  await expect(army.getByRole("link", { name: /Teste Lion/ })).toBeVisible();
  await page.getByLabel("Filtrar listas").fill("lion");
  await expect(card).toBeHidden();
  await expect(army.getByRole("link", { name: /Teste Lion/ })).toBeVisible();
  await page.getByLabel("Filtrar listas").fill("");
  await expect(page.getByLabel("Selecionar Teste Lion")).toHaveCount(0);
  await army.getByRole("article").filter({ hasText: "Teste Lion" }).getByRole("button", { name: "Apagar" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByLabel("Selecionar Teste Lion")).toBeChecked();
  await page.getByLabel("Selecionar O Banquete Podre").check();
  await page.getByLabel("Selecionar O Banquete Podre").uncheck();
  await page.getByRole("button", { name: "Apagar selecionadas (1)" }).click();
  const dialog = page.getByRole("dialog", { name: "Confirmar exclusão" });
  await expect(dialog.getByText(/Apague antes as partidas e os mapas/)).toBeVisible();
  await expect(dialog.getByText("Teste Lion")).toBeVisible();
  await dialog.getByRole("button", { name: "Excluir 1 lista" }).click();
  await expect(army.getByRole("link", { name: /Teste Lion/ })).toHaveCount(0);
  await expect(card).toBeVisible();
  await page.screenshot({ path: "test-results/listas.png", fullPage: true });
});
