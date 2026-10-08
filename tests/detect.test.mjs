// Label detection (web/detect.js) on synthetic carrier pages — run: node --test tests/
// Real pages checked by hand 2026-09-30 (not committed — they carry real addresses): 2 UPS (bordered, turned) →
// border + 90°; 2 FedEx Ship Manager + 1 FedEx Ground test page (no border) → content + 270°; 1 scanned FedEx page
// (upright, instructions down the side) → content + 0°. Each full label found, instructions/header left out.
import test from "node:test";
import assert from "node:assert/strict";
import { detectLabel } from "../web/detect.js";

function page(w, h) {
  const data = new Uint8ClampedArray(w * h * 4).fill(255);
  const fill = (x, y, fw, fh) => { for (let j = y; j < y + fh; j++) for (let i = x; i < x + fw; i++) { const k = (j * w + i) * 4; data[k] = data[k + 1] = data[k + 2] = 0; } };
  const frame = (x, y, fw, fh, t = 3) => { fill(x, y, fw, t); fill(x, y + fh - t, fw, t); fill(x, y, t, fh); fill(x + fw - t, y, t, fh); };
  const bars = (x, y, len, n, vertical) => {                    // a 1D barcode: n bars of varying width
    let p = 0;
    for (let i = 0; i < n; i++) { const bw = 1 + (i * 7) % 4; if (i % 2 === 0) vertical ? fill(x + p, y, bw, len) : fill(x, y + p, len, bw); p += bw + 1 + (i % 3); }
  };
  const text = (x, y, fw, lines, gap = 18) => {                 // rows of "words": thin strokes like real 10 pt text
    for (let l = 0; l < lines; l++) for (let i = x; i < x + fw; i += 9) { fill(i, y + l * gap, 1, 9); if (i % 27 === 0) fill(i, y + l * gap + 4, 5, 1); }
  };
  return { img: { width: w, height: h, data }, fill, frame, bars, text };
}
const inside = (box, [x, y, w, h], tol) => Math.abs(box[0] - x) <= tol && Math.abs(box[1] - y) <= tol &&
  Math.abs(box[0] + box[2] - (x + w)) <= tol && Math.abs(box[1] + box[3] - (y + h)) <= tol;

test("UPS-style: bordered label turned sideways, barcode on the right, instructions below → border, turn 90", () => {
  const p = page(1275, 1650);                                   // letter @150 dpi
  p.text(20, 8, 500, 1);                                        // browser header line
  p.frame(100, 60, 900, 600);
  p.text(140, 120, 300, 8, 30);                                 // addresses (turned text ≈ rows of marks)
  p.bars(700, 90, 540, 70, true);                               // big tracking barcode, right side
  for (let x = 0; x < 1275; x += 12) p.fill(x, 720, 6, 2);      // dotted fold line
  p.text(100, 800, 1000, 14);                                   // instructions
  const r = detectLabel(p.img);
  assert.equal(r.how, "border");
  assert.equal(r.turn, 90);
  assert.ok(inside(r.box, [100, 60, 900, 600], 12), JSON.stringify(r.box));
});

test("FedEx-style: no border, barcode on the left, header line above, instructions far below → content, turn 270", () => {
  const p = page(1275, 1650);
  p.text(20, 8, 700, 1);                                        // browser date/title line: ends y=17, label at y=55
  p.bars(250, 55, 560, 70, true);                               // (0.25 in gap @150 dpi, as measured on FedEx pages)
  p.fill(560, 70, 160, 160); p.fill(560, 310, 160, 160);        // 2D code blocks / logo
  p.text(760, 60, 350, 18, 30);                                 // addresses, right part of the label
  p.text(40, 900, 1100, 12);                                    // instructions, > 1 in below
  const r = detectLabel(p.img);
  assert.equal(r.how, "content");
  assert.equal(r.turn, 270);
  assert.ok(r.box[1] > 20, "header line trimmed: " + JSON.stringify(r.box));
  assert.ok(r.box[1] + r.box[3] < 800, "instructions left out: " + JSON.stringify(r.box));
  assert.ok(r.box[0] <= 255 && r.box[0] + r.box[2] >= 1100, "whole label kept: " + JSON.stringify(r.box));
});

test("upright label screenshot with the barcode at the bottom → no turn", () => {
  const p = page(600, 900);
  p.frame(10, 10, 580, 880);
  p.text(40, 40, 400, 10, 28);
  p.bars(60, 620, 480, 90, false === true);                     // vertical bars near the bottom
  const r = detectLabel(p.img);
  assert.equal(r.turn, 0);
});

test("blank page → null", () => {
  assert.equal(detectLabel(page(400, 500).img), null);
});
