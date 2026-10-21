import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { describe, expect, it } from "vitest";
import { guideMatch } from "./eligibility";

const file = join(dirname(fileURLToPath(import.meta.url)), "../../../fixtures/conditions/guide.json");

describe("R1b guide.json", () => {
  const rows = JSON.parse(readFileSync(file, "utf8").replace(/^\uFEFF/, "")) as {
    name: string;
    node: Record<string, unknown>;
    facts: Record<string, unknown>;
    expected: { include: boolean; conditional: boolean };
  }[];
  for (const row of rows) {
    it(row.name, () => {
      expect(guideMatch(row.node, row.facts)).toEqual(row.expected);
    });
  }
});
