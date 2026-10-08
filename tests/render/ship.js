// UI wiring test for shipping labels: a synthetic letter page (label turned sideways with its barcode on the right,
// instructions below) drawn straight onto a canvas → findLabel() → drawShip() → the 4 × 6 print image.
import { SHIP, findLabel, drawShip } from "./app.js";
setTimeout(() => {
  const out = {};
  try {
    const page = document.createElement("canvas"); page.width = 1275; page.height = 1650;          // letter @150 dpi
    const g = page.getContext("2d");
    g.fillStyle = "#fff"; g.fillRect(0, 0, 1275, 1650); g.fillStyle = "#000"; g.strokeStyle = "#000";
    g.lineWidth = 3; g.strokeRect(100, 60, 900, 600);                                               // label border
    g.font = "bold 40px sans-serif"; g.fillText("SHIP TO: TEST", 140, 160);
    for (let i = 0; i < 90; i++) if (i % 3 !== 1) g.fillRect(700 + i * 3, 120, (i % 5) + 1, 480);    // big barcode, right side
    g.font = "22px sans-serif";
    for (let l = 0; l < 12; l++) g.fillText("Instructions: fold the printed page along the line and place it in a pouch.", 100, 800 + l * 34);
    SHIP.src = page; SHIP.full = g.getImageData(0, 0, 1275, 1650);
    findLabel();
    out.how = SHIP.how; out.turn = SHIP.turn; out.crop = SHIP.crop;
    const c = drawShip(document.createElement("canvas"));
    out.size = [c.width, c.height];
    // after the turn the barcode (right side of the crop) must be at the BOTTOM of the print image
    const px = c.getContext("2d").getImageData(0, 0, c.width, c.height).data, rowInk = y => {
      let n = 0; for (let x = 0; x < c.width; x += 2) n += px[(y * c.width + x) * 4] < 110; return n; };
    let top = 0, bottom = 0;
    for (let y = 0; y < c.height / 2; y += 2) top += rowInk(y);
    for (let y = Math.floor(c.height / 2); y < c.height; y += 2) bottom += rowInk(y);
    out.inkTop = top; out.inkBottom = bottom;
  } catch (e) { out.error = String(e.stack || e); }
  document.body.innerHTML = "<pre id=out>" + JSON.stringify(out) + "</pre>";
}, 1500);
