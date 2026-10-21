import { expect, test as setup } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const authFile = resolve(here, ".auth.json");

setup("grava a sessão", async ({ page }) => {
  let token = process.env.E2E_TOKEN || "";
  try {
    token = readFileSync(resolve(here, "../.e2e-token"), "utf8").trim() || token;
  } catch {
    token = token;
  }
  if (!token) {
    if (process.env.CI) throw new Error("CI sem token e2e");
    await page.context().storageState({ path: authFile });
    return;
  }
  await page.goto("/login");
  await page.getByLabel("Token").fill(token);
  await page.getByRole("button", { name: /entrar/i }).click();
  await expect(page.getByRole("heading", { name: "Listas" })).toBeVisible({ timeout: 15_000 });
  await page.context().storageState({ path: authFile });
});
