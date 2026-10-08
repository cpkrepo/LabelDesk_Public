// Find the shipping label on a full page (UPS/FedEx "print label" pages: the label + instructions + fold line + the
// browser's URL/date), or on a sloppy screenshot. Pure functions over ImageData-like {width, height, data}.
//
// 1. Bordered label (UPS, and most carriers): the largest rectangle made of THIN dark lines. Dotted fold lines aren't
//    continuous; text isn't long enough; solid dark areas (a dark-mode browser bar) are rejected as "not a thin line".
// 2. No border (FedEx): the biggest cluster of dense graphics (barcodes, 2D codes, logo blocks), grown outward until a
//    real whitespace gap — instruction text never forms such a cluster.
// 3. Upright: the main tracking barcode is at the bottom of a UPS or FedEx label → turn so the bars end up at the bottom.
// Returns {box: [x, y, w, h] in source pixels, how: "border" | "content", turn: 0|90|180|270|null} or null.

const DARK = 110;                                            // luminance below this = ink (grey page furniture isn't)

function work(img, maxSide = 1000) {                         // downscaled boolean ink map
  const s = Math.min(1, maxSide / Math.max(img.width, img.height));
  const W = Math.max(1, Math.round(img.width * s)), H = Math.max(1, Math.round(img.height * s));
  const ink = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    // sample the darkest of the source pixels this cell covers (thin 1-px lines must survive downscaling)
    let dark = false;
    const sx0 = Math.floor(x / s), sx1 = Math.min(img.width, Math.floor((x + 1) / s) || sx0 + 1);
    const sy0 = Math.floor(y / s), sy1 = Math.min(img.height, Math.floor((y + 1) / s) || sy0 + 1);
    for (let sy = sy0; sy < Math.max(sy1, sy0 + 1) && !dark; sy++) for (let sx = sx0; sx < Math.max(sx1, sx0 + 1); sx++) {
      const i = (sy * img.width + sx) * 4, a = img.data[i + 3];
      const lum = a < 40 ? 255 : 0.299 * img.data[i] + 0.587 * img.data[i + 1] + 0.114 * img.data[i + 2];
      if (lum < DARK) { dark = true; break; }
    }
    ink[y * W + x] = dark ? 1 : 0;
  }
  return { W, H, ink, s };
}

// long runs of ink along rows (horizontal lines) or columns (vertical lines); gaps ≤ 2 px bridged
function runs(m, horizontal, minLen) {
  const { W, H, ink } = m, out = [];
  const A = horizontal ? H : W, B = horizontal ? W : H;
  for (let a = 0; a < A; a++) {
    let start = -1, gap = 0;
    for (let b = 0; b <= B; b++) {
      const on = b < B && ink[horizontal ? a * W + b : b * W + a];
      if (on) { if (start < 0) start = b; gap = 0; }
      else if (start >= 0 && ++gap > 2) {
        const end = b - gap;
        if (end - start + 1 >= minLen) out.push({ a, b0: start, b1: end });
        start = -1; gap = 0;
      }
    }
  }
  return out;
}

// merge runs on neighbouring rows/cols into lines; drop "lines" that are really filled areas (too thick)
function lines(rs, maxThick, tol) {
  const groups = [];
  for (const r of rs) {
    const g = groups.find(g => r.a - g.a1 <= 1 && Math.abs(r.b0 - g.b0) <= tol && Math.abs(r.b1 - g.b1) <= tol);
    if (g) { g.a1 = r.a; g.b0 = Math.min(g.b0, r.b0); g.b1 = Math.max(g.b1, r.b1); }
    else groups.push({ a0: r.a, a1: r.a, b0: r.b0, b1: r.b1 });
  }
  return groups.filter(g => g.a1 - g.a0 + 1 <= maxThick).map(g => ({ at: (g.a0 + g.a1) / 2, b0: g.b0, b1: g.b1 }));
}

export function findBorder(m) {
  const { W, H } = m;
  const tolX = Math.max(3, W * 0.015), tolY = Math.max(3, H * 0.015);
  const hs = lines(runs(m, true, W * 0.3), Math.max(3, H * 0.012), tolX);
  const vs = lines(runs(m, false, H * 0.15), Math.max(3, W * 0.012), tolY);
  let best = null;
  for (let i = 0; i < hs.length; i++) for (let j = i + 1; j < hs.length; j++) {
    const [t, b] = hs[i].at < hs[j].at ? [hs[i], hs[j]] : [hs[j], hs[i]];
    if (b.at - t.at < H * 0.12 || Math.abs(t.b0 - b.b0) > tolX || Math.abs(t.b1 - b.b1) > tolX) continue;
    const x0 = (t.b0 + b.b0) / 2, x1 = (t.b1 + b.b1) / 2;
    const side = x => vs.some(v => Math.abs(v.at - x) <= tolX && v.b0 <= t.at + tolY && v.b1 >= b.at - tolY);
    if (!side(x0) || !side(x1)) continue;
    const area = (x1 - x0) * (b.at - t.at);
    if (!best || area > best.area) best = { area, box: [x0, t.at, x1 - x0, b.at - t.at] };
  }
  return best && best.area >= W * H * 0.06 ? best.box : null;
}

// ---- cells: ink ratio per small square, and whether it looks like a piece of 1D barcode (parallel bars)
const CELL = 12;                                              // at the ~1000 px working scale ≈ 0.13 in
export function cells(m) {
  const { W, H, ink } = m, cw = Math.ceil(W / CELL), ch = Math.ceil(H / CELL);
  const ratio = new Float32Array(cw * ch), bars = new Int8Array(cw * ch);   // bars: 1 = vertical, 2 = horizontal
  for (let cy = 0; cy < ch; cy++) for (let cx = 0; cx < cw; cx++) {
    const x0 = cx * CELL, y0 = cy * CELL, x1 = Math.min(W, x0 + CELL), y1 = Math.min(H, y0 + CELL);
    const w = x1 - x0, h = y1 - y0;
    if (w < CELL / 2 || h < CELL / 2) continue;
    let n = 0;
    const col = new Uint16Array(w), row = new Uint16Array(h);
    for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) if (ink[y * W + x]) { n++; col[x - x0]++; row[y - y0]++; }
    const r = n / (w * h);
    ratio[cy * cw + cx] = r;
    if (r < 0.2 || r > 0.8) continue;
    // bars: nearly every column is all-ink or all-paper, with several ink/paper changes across the cell
    const pure = (prof, len) => {
      let p = 0, flips = 0, last = -1;
      for (const v of prof) {
        const k = v >= len * 0.8 ? 1 : v <= len * 0.2 ? 0 : -1;
        if (k >= 0) { p++; if (last >= 0 && k !== last) flips++; last = k; }
      }
      return p >= prof.length * 0.85 && flips >= 3;
    };
    bars[cy * cw + cx] = pure(col, h) ? 1 : pure(row, w) ? 2 : 0;
  }
  return { cw, ch, ratio, bars };
}

// the biggest cluster of dense graphics (barcodes, 2D codes, logo blocks) — instruction text never gets this dense
function denseCluster(c) {
  const { cw, ch, ratio, bars } = c, seen = new Uint8Array(cw * ch);
  const dense = i => bars[i] || ratio[i] >= 0.45;
  let best = null;
  for (let i = 0; i < cw * ch; i++) {
    if (seen[i] || !dense(i)) continue;
    const stack = [i], members = [];
    seen[i] = 1;
    while (stack.length) {
      const j = stack.pop(); members.push(j);
      const jx = j % cw, jy = (j - jx) / cw;
      for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) {          // bridge gaps of one cell
        const nx = jx + dx, ny = jy + dy, k = ny * cw + nx;
        if (nx >= 0 && ny >= 0 && nx < cw && ny < ch && !seen[k] && dense(k)) { seen[k] = 1; stack.push(k); }
      }
    }
    const barCells = members.filter(j => bars[j]).length;
    const score = members.length + 2 * barCells;
    if (barCells >= 3 && (!best || score > best.score)) best = { score, members };
  }
  if (!best) return null;
  let x0 = cw, y0 = ch, x1 = -1, y1 = -1;
  for (const j of best.members) { const x = j % cw, y = (j - x) / cw; x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
  return [x0 * CELL, y0 * CELL, (x1 + 1) * CELL, (y1 + 1) * CELL];
}

// grow a box outward while the strip next to it still has ink; stop at a real gap. Measured on real FedEx pages
// (300 dpi, letter): gaps INSIDE a label reach 0.37", the instructions start ≥ 1" away — so the stop gap is 5 % of
// the page (≈ 0.55"). The browser's date/title line (0.25" above) gets absorbed and is trimmed off by trimEdges().
function grow(m, [x0, y0, x1, y1]) {
  const { W, H, ink } = m;
  const gapX = Math.max(6, Math.round(Math.max(W, H) * 0.05)), gapY = gapX;
  const colInk = (x, a, b) => { let n = 0; for (let y = a; y < b; y++) n += ink[y * W + x]; return n > Math.max(1, (b - a) * 0.004); };
  const rowInk = (y, a, b) => { let n = 0; for (let x = a; x < b; x++) n += ink[y * W + x]; return n > Math.max(1, (b - a) * 0.004); };
  const side = (pos, dir, limit, gap, has) => {           // walk outward, remember the last line with ink
    let last = pos, empty = 0;
    for (let p = pos + dir; dir > 0 ? p < limit : p >= 0; p += dir) {
      if (has(p)) { last = p; empty = 0; } else if (++empty >= gap) break;
    }
    return last;
  };
  for (let pass = 0; pass < 6; pass++) {
    const before = [x0, y0, x1, y1].join();
    x0 = side(x0, -1, 0, gapX, x => colInk(x, y0, y1));
    x1 = side(x1 - 1, 1, W, gapX, x => colInk(x, y0, y1)) + 1;
    y0 = side(y0, -1, 0, gapY, y => rowInk(y, x0, x1));
    y1 = side(y1 - 1, 1, H, gapY, y => rowInk(y, x0, x1)) + 1;
    if ([x0, y0, x1, y1].join() === before) break;
  }
  return [x0, y0, x1 - x0, y1 - y0];
}

// drop thin, text-only strips at the box edges that are set apart by a gap (browser header/footer lines, a page
// title): a strip ≤ 4.5 % of the page thick, ≥ 2 % away from the rest, with no barcode/dense cells in it
function trimEdges(m, c, [bx, by, bw, bh]) {
  const { W, H, ink } = m, D = Math.max(W, H), gapMin = Math.max(4, Math.round(D * 0.02)), thin = D * 0.045;
  const denseIn = (x0, y0, x1, y1) => {
    for (let cy = Math.floor(y0 / CELL); cy <= Math.floor((y1 - 1) / CELL); cy++)
      for (let cx = Math.floor(x0 / CELL); cx <= Math.floor((x1 - 1) / CELL); cx++) {
        const i = cy * c.cw + cx;
        if (cx >= 0 && cy >= 0 && cx < c.cw && cy < c.ch && (c.bars[i] || c.ratio[i] >= 0.55)) return true;   // bars, 2D code, logo
      }
    return false;
  };
  const bands = (horizontal) => {                             // ink bands along y (horizontal) or x
    const len = horizontal ? bh : bw, out = [];
    let start = -1, empty = 0;
    for (let i = 0; i <= len; i++) {
      let has = false;
      if (i < len) {
        if (horizontal) { const y = by + i; for (let x = bx; x < bx + bw && !has; x++) has = !!ink[y * W + x]; }
        else { const x = bx + i; for (let y = by; y < by + bh && !has; y++) has = !!ink[y * W + x]; }
      }
      if (has) { if (start < 0) start = i; empty = 0; }
      else if (start >= 0 && (++empty >= gapMin || i === len)) { out.push([start, i - empty]); start = -1; empty = 0; }
    }
    return out;
  };
  for (const horizontal of [true, false]) {
    const b = bands(horizontal);
    if (b.length < 2) continue;
    const box = (s, e) => horizontal ? [bx, by + s, bx + bw, by + e + 1] : [bx + s, by, bx + e + 1, by + bh];
    let first = 0, last = b.length - 1;
    while (first < last && b[first][1] - b[first][0] < thin && !denseIn(...box(...b[first]))) first++;
    while (last > first && b[last][1] - b[last][0] < thin && !denseIn(...box(...b[last]))) last--;
    const s = b[first][0], e = b[last][1];
    if (horizontal) { by += s; bh = e - s + 1; } else { bx += s; bw = e - s + 1; }
  }
  return [bx, by, bw, bh];
}

export function findContent(m) {
  const c = cells(m), seed = denseCluster(c);
  return seed ? trimEdges(m, c, grow(m, seed)) : null;
}

// which way is up: the main tracking barcode sits at the bottom of UPS and FedEx labels alike. Turn the crop (0/90/180/270°
// clockwise) so the bar cells' centre of mass ends up at the bottom. null when there's no barcode to go by.
export function uprightTurn(m, [bx, by, bw, bh]) {
  const c = cells(m);
  let sx = 0, sy = 0, n = 0;
  for (let cy = 0; cy < c.ch; cy++) for (let cx = 0; cx < c.cw; cx++) {
    if (!c.bars[cy * c.cw + cx]) continue;
    const x = (cx + 0.5) * CELL, y = (cy + 0.5) * CELL;
    if (x < bx || x > bx + bw || y < by || y > by + bh) continue;
    sx += (x - bx) / bw - 0.5; sy += (y - by) / bh - 0.5; n++;
  }
  if (n < 6) return null;
  const dx = sx / n, dy = sy / n;
  if (Math.abs(dx) < 0.04 && Math.abs(dy) < 0.04) return null;
  if (Math.abs(dy) >= Math.abs(dx)) return dy > 0 ? 0 : 180;    // barcode low → upright; high → upside down
  return dx > 0 ? 90 : 270;                                     // barcode on the right → turn clockwise; left → counter
}

export function detectLabel(img) {
  const m = work(img);
  let box = findBorder(m), how = "border";
  if (!box) { box = findContent(m); how = "content"; }
  if (!box) return null;
  const turn = uprightTurn(m, box);
  const pad = 2;                                              // keep the border line itself
  const [x, y, w, h] = box;
  const X = Math.max(0, (x - pad) / m.s), Y = Math.max(0, (y - pad) / m.s);
  return { how, turn, box: [Math.round(X), Math.round(Y), Math.round(Math.min(img.width - X, (w + 2 * pad + 1) / m.s)),
                            Math.round(Math.min(img.height - Y, (h + 2 * pad + 1) / m.s))] };
}
