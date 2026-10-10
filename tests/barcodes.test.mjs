// Every barcode LabelDesk draws must scan: render each symbology (web/barcodes.js) to an image and decode it with zbar
// (zbarimg — the same reader LabelDesk's shipping check uses). Skipped where zbarimg isn't installed.
//   node --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { raster, encode } from "../web/barcodes.js";

let zbar = true;
try { execFileSync("zbarimg", ["--version"], { stdio: "ignore" }); } catch { zbar = false; }

function decode(sym, text, module = 3) {
  const r = raster(sym, text, module);
  const dir = mkdtempSync(join(tmpdir(), "ldbc-")), f = join(dir, "b.pbm");
  const rows = [];
  for (let y = 0; y < r.h; y++) { let s = ""; for (let x = 0; x < r.w; x++) s += r.px(x, y) ? "1" : "0"; rows.push(s); }
  writeFileSync(f, `P1\n${r.w} ${r.h}\n${rows.join("\n")}\n`);
  try {
    return execFileSync("zbarimg", ["--quiet", "--raw", f], { encoding: "utf8" }).trim();
  } finally { rmSync(dir, { recursive: true }); }
}

const CASES = [
  ["code128", "75013"], ["code128", "Ticket#75013 a-Z"],
  ["code39", "75013"], ["code39", "PF3XK2LQ"], ["code39", "AB-12 ./$+%"],
  ["upca", "03600029145", "036000291452"], ["upca", "036000291452"],
  ["ean13", "400638133393", "4006381333931"],
  ["qr", "75013"],
  ["qr", "https://support.example.com/ticket?asset=PF3XK2LQ&company=Acme%20Dental"],                // ~v5
  ["qr", "https://example.com/" + "x".repeat(120)],                                                   // v7+: version bits
  ["qr", "Ünïcödé ✓ " + "y".repeat(200)],                                                            // v10+, UTF-8
];

for (const [sym, text, expect] of CASES) {
  test(`${sym}: "${text.slice(0, 40)}${text.length > 40 ? "…" : ""}" scans`, { skip: !zbar && "zbarimg not installed" }, () => {
    let got = decode(sym, text);
    if (sym === "upca" && got.length === 13 && got[0] === "0") got = got.slice(1);   // zbar reports UPC-A as its EAN-13 form
    assert.equal(got, expect ?? text);
  });
}

test("bad input is refused, not drawn wrong", () => {
  assert.throws(() => encode("upca", "12345"));
  assert.throws(() => encode("ean13", "4006381333932"));            // wrong check digit
  assert.throws(() => encode("code39", "a*b"));
  assert.throws(() => encode("code128", "naïve"));
  assert.throws(() => encode("qr", "z".repeat(500)));                // more than a label-sized QR holds
});
