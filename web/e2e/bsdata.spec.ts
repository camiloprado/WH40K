import { expect, test } from "@playwright/test";

const SHA = "d506fcc0ee4b4babdda03e71dffd4e1e3cf5bcbf";
const empty = { added: [], changed: [], kept: [] };
const counts = (added = 0, changed = 0, kept = 0, same = 0) => ({ added, changed, kept, same });

test("catálogo mostra o diff do BSData antes de aplicar", async ({ page }) => {
  let applied = false;
  const imports: unknown[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace("/api/v1", "");
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/factions") return json([{ id: 1, name: "Chaos - Chaos Daemons" }]);
    if (path === "/abilities")
      return json(applied ? [{ id: 7, kind: "unit", datasheet_id: 3, name: "Twin Oaths", source: "bsdata", is_hypothesis: true }] : []);
    if (path === "/effects")
      return json(applied ? [{ id: 70, ability_id: 7, phase: "command", turn_owner: "own", effect_text: "Resumo pendente", source: "bsdata", choice_options: ["A", "B", "C"], choice_count: 2 }] : []);
    if (path === "/datasheets") return json([{ id: 3, name: "Cinder Lord", faction_id: 1 }]);
    if (path === "/detachments") return json([]);
    if (path === "/bsdata/imports") return json(imports);
    if (path === "/bsdata/repos/wh40k-11e/catalogues")
      return json({
        repo: "wh40k-11e",
        sha: SHA,
        date: "2026-10-14T10:00:00Z",
        message: "Codex update",
        files: [
          { name: "Chaos - Chaos Daemons.json", size: 10, library: false, system: false },
          { name: "Chaos - Chaos Daemons Library.json", size: 10, library: true, system: false },
          { name: "Warhammer 40,000.json", size: 10, library: false, system: true },
        ],
      });
    if (path === "/bsdata/import") {
      const body = route.request().postDataJSON();
      expect(body).toMatchObject({ repo: "wh40k-11e", sha: SHA, catalogue: "Chaos - Chaos Daemons.json", faction_id: null });
      applied = body.apply;
      if (applied) imports.unshift({ catalogue: body.catalogue, sha: SHA, imported_at: "2026-10-15T12:00:00Z" });
      return json({
        catalogue: body.catalogue,
        faction: { id: 1, name: "Chaos - Chaos Daemons", created: false },
        applied: body.apply,
        changes: {
          datasheets: { ...empty, changed: [{ name: "Poxbringer", fields: ["toughness", "keywords"] }] },
          weapons: { ...empty, added: ["Poxbringer · Foul balesword"] },
          abilities: { ...empty, added: ["Cinder Lord · Twin Oaths"] },
          effects: { ...empty, added: [{ name: "Cinder Lord · Twin Oaths", phase: "command", options: 3, count: 2 }] },
          detachments: empty,
          enhancements: empty,
        },
        counts: {
          datasheets: counts(0, 1, 0, 9),
          weapons: counts(1),
          abilities: counts(1),
          effects: counts(1),
          detachments: counts(0, 0, 0, 9),
          enhancements: counts(),
        },
      });
    }
    return json([]);
  });

  await page.goto("/catalog");
  const panel = page.getByRole("region", { name: "Atualizar do BSData" });
  await panel.getByRole("button", { name: "Buscar facções" }).click();
  const catalogue = panel.getByLabel("Catálogo");
  await expect(catalogue).toHaveValue("Chaos - Chaos Daemons.json");
  await expect(catalogue.locator("option")).toHaveText(["Escolha…", "Chaos - Chaos Daemons"]);
  await panel.getByRole("button", { name: "Ver o que muda" }).click();
  await expect(panel.getByText("+0 · ~1 · mantidos 0 · iguais 9")).toBeVisible();
  await panel.getByText("Fichas", { exact: true }).click();
  await expect(panel.getByText("Poxbringer (toughness, keywords)")).toBeVisible();
  await page.screenshot({ path: "test-results/bsdata-diff.png", fullPage: true });
  await panel.getByRole("button", { name: "Aplicar" }).click();
  await expect(panel.getByText(/Pronto/)).toBeVisible();
  await expect(panel.getByText(/Última: Chaos - Chaos Daemons · commit d506fcc/)).toBeVisible();
  await expect(page.getByText("BSData", { exact: true })).toBeVisible();
  await page.getByLabel("Buscar habilidade").fill("nada-assim");
  await expect(page.getByText("Nada com esse filtro.").first()).toBeVisible();
});
