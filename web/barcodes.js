// Barcodes LabelDesk draws itself (no library, works offline, same on every PC) — the preview is the print.
//   1D: Code 128 (set B), Code 39, UPC-A, EAN-13 — what the shop's 1D scanner reads (keep anything a technician scans 1D)
//   2D: QR (byte mode, error correction M, versions 1–15) — for customers' phones only (the shop scanner can't read QR)
// encode(symbology, text) → {type: "1d", widths: "2122…"} (module widths, bar first) or {type: "2d", size, dark(x, y)}
// draw(ctx, symbology, text, x, y, w, h) draws it into the box at whole-pixel modules (crisp on a 300 dpi head).
// Checked by decoding real renders with zbar: tests/barcodes.test.mjs.

export const SYMBOLOGIES = { code128: "Code 128", code39: "Code 39", upca: "UPC-A", ean13: "EAN-13", qr: "QR code" };

// ------------------------------------------------------------------ Code 128 set B: any printable ASCII
export const C128 = ["212222","222122","222221","121223","121322","131222","122213","122312","132212","221213","221312","231212",
  "112232","122132","122231","113222","123122","123221","223211","221132","221231","213212","223112","312131","311222","321122",
  "321221","312212","322112","322211","212123","212321","232121","111323","131123","131321","112313","132113","132311","211313",
  "231113","231311","112133","112331","132131","113123","113321","133121","313121","211331","231131","213113","213311","213131",
  "311123","311321","331121","312113","312311","332111","314111","221411","431111","111224","111422","121124","121421","141122",
  "141221","112214","112412","122114","122411","142112","142211","241211","221114","413111","241112","134111","111242","121142",
  "121241","114212","124112","124211","411212","421112","421211","212141","214121","412121","111143","111341","131141","114113",
  "114311","411113","411311","113141","114131","311141","411131","211412","211214","211232","2331112"];
export function code128(text) {
  const codes = [104];                                        // Start B
  for (const ch of text) {
    const c = ch.charCodeAt(0) - 32;
    if (c < 0 || c > 94) throw new Error("barcode: only plain characters");
    codes.push(c);
  }
  codes.push(codes.reduce((s, c, i) => s + c * (i || 1), 0) % 103, 106);   // checksum, Stop
  return codes.map(c => C128[c]).join("");
}

// ------------------------------------------------------------------ Code 39: 0-9 A-Z - . space $ / + % (lower case → upper)
const C39_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-. $/+%*";
const C39 = ["111221211","211211112","112211112","212211111","111221112","211221111","112221111","111211212","211211211",
  "112211211","211112112","112112112","212112111","111122112","211122111","112122111","111112212","211112211","112112211",
  "111122211","211111122","112111122","212111121","111121122","211121121","112121121","111111222","211111221","112111221",
  "111121221","221111112","122111112","222111111","121121112","221121111","122121111","121111212","221111211","122111211",
  "121212111","121211121","121112121","111212121","121121211"];   // n = 1, w = 2 (wide = 2.5× would be nicer; 2× scans fine)
export function code39(text) {
  if (text.includes("*")) throw new Error('Code 39 can\'t hold "*"');
  const t = "*" + text.toUpperCase() + "*";
  return [...t].map(ch => {
    const i = C39_CHARS.indexOf(ch);
    if (i < 0) throw new Error(`Code 39 can't hold "${ch}"`);
    return C39[i].replace(/2/g, "3") + "1";                   // wide = 3 modules (2.5–3 is the spec range) + gap
  }).join("").slice(0, -1);
}

// ------------------------------------------------------------------ UPC-A / EAN-13 (digits; the check digit is added/checked)
const EAN_L = ["3211","2221","2122","1411","1132","1231","1114","1312","1213","3112"];
const EAN_G = ["1123","1222","2212","1141","2311","1321","4111","2131","3121","2113"];
const EAN_PARITY = ["LLLLLL","LLGLGG","LLGGLG","LLGGGL","LGLLGG","LGGLLG","LGGGLL","LGLGLG","LGLGGL","LGGLGL"];
const checkDigit = d => (10 - ([...d].reverse().reduce((s, c, i) => s + +c * (i % 2 ? 1 : 3), 0) % 10)) % 10;
export function ean13(text) {
  let d = String(text).replace(/\s/g, "");
  if (!/^\d{12,13}$/.test(d)) throw new Error("EAN-13 needs 12 or 13 digits");
  if (d.length === 12) d += checkDigit(d);
  else if (+d[12] !== checkDigit(d.slice(0, 12))) throw new Error("EAN-13 check digit is wrong");
  const par = EAN_PARITY[+d[0]];
  let w = "111";
  for (let i = 1; i <= 6; i++) w += (par[i - 1] === "L" ? EAN_L : EAN_G)[+d[i]];
  w += "11111";
  for (let i = 7; i <= 12; i++) w += EAN_L[+d[i]];        // right half: R patterns = L widths, starting with a bar
  return w + "111";
}
export function upca(text) {
  const d = String(text).replace(/\s/g, "");
  if (!/^\d{11,12}$/.test(d)) throw new Error("UPC-A needs 11 or 12 digits");
  return ean13("0" + d);                                      // UPC-A = EAN-13 with a leading 0
}

// ------------------------------------------------------------------ QR (ISO/IEC 18004): byte mode, level M, versions 1–15
const QR_EC_M = [[10,1,16],[16,1,28],[26,1,44],[18,2,32],[24,2,43],[16,4,27],[18,4,31],[22,2,38,2,39],[22,3,36,2,37],
  [26,4,43,1,44],[30,1,50,4,51],[22,6,36,2,37],[22,8,37,1,38],[24,4,40,5,41],[24,5,41,5,42]];   // ecPerBlock, n1, k1[, n2, k2]
const QR_ALIGN = [[],[6,18],[6,22],[6,26],[6,30],[6,34],[6,22,38],[6,24,42],[6,26,46],[6,28,50],[6,30,54],[6,32,58],[6,34,62],
  [6,26,46,66],[6,26,48,70]];
const GF_EXP = new Uint8Array(512), GF_LOG = new Uint8Array(256);
for (let i = 0, x = 1; i < 255; i++) { GF_EXP[i] = x; GF_LOG[x] = i; x <<= 1; if (x & 256) x ^= 0x11d; }
for (let i = 255; i < 512; i++) GF_EXP[i] = GF_EXP[i - 255];
const gfMul = (a, b) => (a && b ? GF_EXP[GF_LOG[a] + GF_LOG[b]] : 0);
function rsGenerator(n) {
  let g = [1];
  for (let i = 0; i < n; i++) {
    const next = new Array(g.length + 1).fill(0);
    g.forEach((c, j) => { next[j] ^= c; next[j + 1] ^= gfMul(c, GF_EXP[i]); });
    g = next;
  }
  return g;
}
function rsRemainder(data, n) {
  const g = rsGenerator(n), r = new Array(n).fill(0);
  for (const b of data) {
    const f = b ^ r.shift(); r.push(0);
    for (let i = 0; i < n; i++) r[i] ^= gfMul(g[i + 1], f);
  }
  return r;
}
export function qr(text) {
  const bytes = [...new TextEncoder().encode(text)];
  let ver = 0, spec;
  for (let v = 1; v <= 15; v++) {
    spec = QR_EC_M[v - 1];
    const dataCw = spec[1] * spec[2] + (spec[3] || 0) * (spec[4] || 0);
    if (4 + (v < 10 ? 8 : 16) + 8 * bytes.length <= dataCw * 8) { ver = v; break; }
  }
  if (!ver) throw new Error("too much text for a QR code on a label");
  const [ecn, n1, k1, n2 = 0, k2 = 0] = spec, dataCw = n1 * k1 + n2 * k2;
  // data bits: mode 0100, length, bytes, terminator, pad to bytes, pad codewords
  const bits = [];
  const put = (val, len) => { for (let i = len - 1; i >= 0; i--) bits.push((val >> i) & 1); };
  put(4, 4); put(bytes.length, ver < 10 ? 8 : 16); bytes.forEach(b => put(b, 8));
  put(0, Math.min(4, dataCw * 8 - bits.length));
  while (bits.length % 8) bits.push(0);
  const cw = [];
  for (let i = 0; i < bits.length; i += 8) cw.push(bits.slice(i, i + 8).reduce((s, b) => s * 2 + b, 0));
  for (let p = 0; cw.length < dataCw; p++) cw.push(p % 2 ? 0x11 : 0xec);
  // blocks + error correction, interleaved
  const blocks = [];
  let at = 0;
  for (let i = 0; i < n1 + n2; i++) { const k = i < n1 ? k1 : k2; blocks.push(cw.slice(at, at + k)); at += k; }
  const ecs = blocks.map(b => rsRemainder(b, ecn));
  const out = [];
  for (let i = 0; i < Math.max(k1, k2); i++) blocks.forEach(b => { if (i < b.length) out.push(b[i]); });
  for (let i = 0; i < ecn; i++) ecs.forEach(e => out.push(e[i]));
  // matrix: function patterns first
  const size = 17 + 4 * ver, M = [...Array(size)].map(() => new Array(size).fill(null));
  const finder = (r, c) => {
    for (let y = -1; y <= 7; y++) for (let x = -1; x <= 7; x++) {
      if (r + y < 0 || r + y >= size || c + x < 0 || c + x >= size) continue;
      const on = y >= 0 && y <= 6 && x >= 0 && x <= 6 && (y === 0 || y === 6 || x === 0 || x === 6 || (y >= 2 && y <= 4 && x >= 2 && x <= 4));
      M[r + y][c + x] = on;
    }
  };
  finder(0, 0); finder(0, size - 7); finder(size - 7, 0);
  for (let i = 8; i < size - 8; i++) { M[6][i] = i % 2 === 0; M[i][6] = i % 2 === 0; }
  const al = QR_ALIGN[ver - 1];
  for (const r of al) for (const c of al) {
    const last = al[al.length - 1];
    if ((r === 6 && c === 6) || (r === 6 && c === last) || (r === last && c === 6)) continue;   // the finder corners
    for (let y = -2; y <= 2; y++) for (let x = -2; x <= 2; x++) M[r + y][c + x] = Math.max(Math.abs(x), Math.abs(y)) !== 1;
  }
  M[size - 8][8] = true;                                       // dark module
  const reserve = () => {                                      // format (+ version) areas, filled after masking
    for (let i = 0; i < 9; i++) { if (M[8][i] === null) M[8][i] = false; if (M[i][8] === null) M[i][8] = false; }
    for (let i = 0; i < 8; i++) { if (M[8][size - 1 - i] === null) M[8][size - 1 - i] = false; if (M[size - 1 - i][8] === null) M[size - 1 - i][8] = false; }
    if (ver >= 7) for (let i = 0; i < 6; i++) for (let j = 0; j < 3; j++) { M[i][size - 11 + j] = false; M[size - 11 + j][i] = false; }
  };
  reserve();
  const isFn = M.map(row => row.map(v => v !== null));
  // data, zig-zag from the bottom right
  const dbits = [];
  out.forEach(b => { for (let i = 7; i >= 0; i--) dbits.push((b >> i) & 1); });
  let k = 0;
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let vert = 0; vert < size; vert++) for (let j = 0; j < 2; j++) {
      const x = right - j, up = ((right + 1) & 2) === 0, y = up ? size - 1 - vert : vert;
      if (!isFn[y][x]) M[y][x] = k < dbits.length ? !!dbits[k++] : false;
    }
  }
  const MASKS = [(y, x) => (y + x) % 2 === 0, y => y % 2 === 0, (y, x) => x % 3 === 0, (y, x) => (y + x) % 3 === 0,
    (y, x) => (Math.floor(y / 2) + Math.floor(x / 3)) % 2 === 0, (y, x) => (y * x) % 2 + (y * x) % 3 === 0,
    (y, x) => ((y * x) % 2 + (y * x) % 3) % 2 === 0, (y, x) => ((y + x) % 2 + (y * x) % 3) % 2 === 0];
  const formatBits = mask => {                                 // level M = 00
    let d = (0 << 3) | mask, r = d << 10;
    for (let i = 14; i >= 10; i--) if ((r >> i) & 1) r ^= 0x537 << (i - 10);
    return ((d << 10) | r) ^ 0x5412;
  };
  const place = (G, mask) => {
    const f = formatBits(mask), bit = i => ((f >> i) & 1) === 1;
    // G[row][col]; positions per ISO/IEC 18004 Figure 25 (as in Nayuki's reference implementation)
    for (let i = 0; i <= 5; i++) G[i][8] = bit(i);
    G[7][8] = bit(6); G[8][8] = bit(7); G[8][7] = bit(8);
    for (let i = 9; i < 15; i++) G[8][14 - i] = bit(i);
    for (let i = 0; i < 8; i++) G[8][size - 1 - i] = bit(i);
    for (let i = 8; i < 15; i++) G[size - 15 + i][8] = bit(i);
    G[size - 8][8] = true;
    if (ver >= 7) {
      let r = ver << 12;
      for (let i = 17; i >= 12; i--) if ((r >> i) & 1) r ^= 0x1f25 << (i - 12);
      const v = (ver << 12) | r;
      for (let i = 0; i < 18; i++) { const b = ((v >> i) & 1) === 1, a = Math.floor(i / 3), c = size - 11 + (i % 3); G[a][c] = b; G[c][a] = b; }
    }
  };
  const penalty = G => {
    let p = 0;
    const line = get => {
      for (let i = 0; i < size; i++) {
        let run = 1;
        for (let j = 1; j < size; j++) {
          if (get(i, j) === get(i, j - 1)) { run++; if (run === 5) p += 3; else if (run > 5) p++; } else run = 1;
        }
        for (let j = 0; j + 10 < size; j++) {
          const s = [...Array(11)].map((_, t) => get(i, j + t) ? 1 : 0).join("");
          if (s === "10111010000" || s === "00001011101") p += 40;
        }
      }
    };
    line((i, j) => G[i][j]); line((i, j) => G[j][i]);
    for (let y = 0; y < size - 1; y++) for (let x = 0; x < size - 1; x++) {
      const c = G[y][x];
      if (c === G[y][x + 1] && c === G[y + 1][x] && c === G[y + 1][x + 1]) p += 3;
    }
    const dark = G.flat().filter(Boolean).length;
    return p + Math.floor(Math.abs(dark * 20 - size * size * 10) / (size * size)) * 10;
  };
  let best = null, bestP = Infinity;
  for (let m = 0; m < 8; m++) {
    const G = M.map((row, y) => row.map((v, x) => (isFn[y][x] ? v : v !== MASKS[m](y, x))));
    place(G, m);
    const p = penalty(G);
    if (p < bestP) { bestP = p; best = G; }
  }
  return best;
}

// ------------------------------------------------------------------ one entry point
export function encode(symbology, text) {
  const t = String(text ?? "");
  if (symbology === "qr") { const m = qr(t); return { type: "2d", size: m.length, dark: (x, y) => m[y][x] }; }
  const widths = { code128, code39, upca, ean13 }[symbology || "code128"];
  if (!widths) throw new Error(`unknown barcode type ${symbology}`);
  return { type: "1d", widths: widths(t) };
}

export function draw(ctx, symbology, text, x, y, w, h) {
  const e = encode(symbology, text);
  [x, y, w, h] = [Math.round(x), Math.round(y), Math.floor(w), Math.floor(h)];   // whole pixels: no grey module edges
  if (e.type === "2d") {
    const quiet = 4, n = e.size + 2 * quiet, m = Math.max(1, Math.floor(Math.min(w, h) / n));   // whole pixels per module
    const ox = x + Math.round((w - m * e.size) / 2), oy = y + Math.round((h - m * e.size) / 2);
    for (let r = 0; r < e.size; r++) for (let c = 0; c < e.size; c++) if (e.dark(c, r)) ctx.fillRect(ox + c * m, oy + r * m, m, m);
    return;
  }
  const quiet = symbology === "upca" || symbology === "ean13" ? 9 : 10;
  const modules = [...e.widths].reduce((s, d) => s + +d, 0) + 2 * quiet;
  const m = Math.max(1, Math.floor(w / modules));
  let cx = x + Math.round((w - m * (modules - 2 * quiet)) / 2);
  [...e.widths].forEach((d, i) => { if (i % 2 === 0) ctx.fillRect(cx, y, m * d, h); cx += m * d; });
}

// a 1-bit image of a barcode (for tests and anything without a canvas): {w, h, px(x, y) → dark}
export function raster(symbology, text, module = 3, height = 120) {
  const e = encode(symbology, text);
  if (e.type === "2d") {
    const q = 4, n = (e.size + 2 * q) * module;
    return { w: n, h: n, px: (x, y) => { const c = Math.floor(x / module) - q, r = Math.floor(y / module) - q;
      return c >= 0 && r >= 0 && c < e.size && r < e.size && e.dark(c, r); } };
  }
  const q = 12, cols = [];
  [...e.widths].forEach((d, i) => { for (let k = 0; k < +d * module; k++) cols.push(i % 2 === 0); });
  const w = cols.length + 2 * q * module;
  return { w, h: height, px: x => !!cols[x - q * module] };
}
