import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const root = css.slice(css.indexOf(":root"), css.indexOf("}", css.indexOf(":root")));
const token = (name) => {
  const match = root.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{3,6})`));
  if (!match) throw new Error(`token ${name}`);
  const hex = match[1];
  if (hex.length === 4) return `#${hex[1]}${hex[1]}${hex[2]}${hex[2]}${hex[3]}${hex[3]}`;
  return hex;
};
function lin(channel) {
  const value = channel / 255;
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}
function lum(hex) {
  const n = parseInt(hex.slice(1), 16);
  const r = lin((n >> 16) & 255);
  const g = lin((n >> 8) & 255);
  const b = lin(n & 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function ratio(a, b) {
  const left = lum(a);
  const right = lum(b);
  const [hi, lo] = left > right ? [left, right] : [right, left];
  return (hi + 0.05) / (lo + 0.05);
}
const pairs = [
  ["--battle_shock", "--on-battle_shock"],
  ["--end_of_round", "--on-end_of_round"],
  ["--round_start", "--on-round_start"],
  ["--command", "--on-command"],
  ["--movement", "--on-movement"],
  ["--shooting", "--on-shooting"],
  ["--charge", "--on-charge"],
  ["--fight", "--on-fight"],
  ["--end_of_turn", "--on-end_of_turn"],
];
let failed = 0;
for (const [bg, fg] of pairs) {
  const score = ratio(token(bg), token(fg));
  if (score < 4.5) {
    failed += 1;
    console.error(`${bg} ${score.toFixed(2)}`);
  }
}
if (failed) process.exit(1);
console.log(`contraste ok (${pairs.length} fases)`);
