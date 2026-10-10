// Label designer: a layout for any DYMO label the 550 Turbo / 5XL take (server/stocks.json, from DYMO's own drivers).
// Layouts use the template format of imported .dymo files (template.js: objects in inches on the label, text with
// {company} {customer} {ticket} {received} {serial} {bin} {item}), so a tag-sized layout can be the inventory tag's
// layout too. Drawn by the same code that prints — the preview is the print. Saved per PC; "Share with the shop" puts it
// in the repo's templates/ (the owner approves it like any change) and every PC then lists it.
import { api, toast, printCanvas, drawLabel, designSize, usDate, isTagLayout } from "./app.js";
import { drawTemplate, loadTemplates, saveTemplates, setActiveTemplate, parseDymo, templateImagesReady, symbologyOf } from "./template.js";
import { draw as drawCode, encode } from "./barcodes.js";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const DPI = 300;
const FIELDS = [["{company}", "Company"], ["{customer}", "Customer name"], ["{ticket}", "Ticket #"], ["{received}", "Received"],
                ["{serial}", "Serial #"], ["{bin}", "Shelf / bin"], ["{item}", "Accessory"]];
const CODES = [["Code128Auto", "Code 128"], ["Code39", "Code 39"], ["UpcA", "UPC-A"], ["Ean13", "EAN-13"], ["QRCode", "QR code (phones)"]];
const SAMPLE = { customer: "Acme Dental Group", contact: "Jane Smith", ticket: "75013", received: new Date().toISOString().slice(0, 10),
                 serial: "PF3XK2LQ", bin: "B3", item: "Charger" };

let STOCKS = [], SHOP = [], tpl = null, sel = -1, dirty = false;

// a stocks.json entry → the label shape app.js draws with (same as the server's stock_label)
const labOf = s => s && ({ name: s.name, stock: s.name, page: s.page, width_in: s.size_pt[0] / 72, height_in: s.size_pt[1] / 72,
                          safe_in: s.area_pt.map(v => v / 72), sku: s.sku, printers: s.printers });
const stockOf = id => STOCKS.find(s => s.id === id) || STOCKS.find(s => s.id === "w79h252") || STOCKS[0];
const inches = v => Math.round(v * 1000) / 1000;

function fresh(stockId = "w79h252") {
  const s = stockOf(stockId);
  const t = { id: `d${Date.now()}`, name: "New layout", stock: s.id, orientation: s.size_pt[1] > s.size_pt[0] * 1.2 ? "Landscape" : "Portrait", objects: [] };
  const [DW, DH] = designSize(labOf(s), t), w = DW / DPI, h = DH / DPI;
  t.rect = { x: 0, y: 0, w, h };
  t.objects = [text("{company}", 0.04, 0.03, w - 0.08, h * 0.3, 20, true),
               text("Ticket#: {ticket}", 0.04, h * 0.36, w - 0.08, h * 0.22, 14, true),
               { kind: "barcode", name: "Barcode", x: 0.04, y: h * 0.62, w: w * 0.7, h: h * 0.33, halign: "Left", format: "{ticket}", symbology: "Code128Auto" }];
  return t;
}
function text(format, x, y, w, h, size = 12, bold = false) {
  return { kind: "text", name: "Text", x, y, w, h, halign: "Left", valign: "Middle", fit: "ShrinkToFit",
           lines: [{ size, bold, italic: false }], format, sample: format };
}

// ---- the stage: the design space at 300 dpi, CSS-scaled; selection outline + resize corner drawn on top
function dims() {
  const lab = labOf(stockOf(tpl.stock));
  const [DW, DH] = designSize(lab, tpl);
  const r = tpl.rect || { x: 0, y: 0, w: DW / DPI, h: DH / DPI };
  const s = Math.min(DW / (r.w * DPI), DH / (r.h * DPI));            // = drawTemplate's (1 for designer layouts)
  return { lab, DW, DH, r, s, toPx: (v, o) => (v - o) * DPI * s, toIn: (p, o) => p / (DPI * s) + o };
}
function fields() {
  const f = {};
  $$(".dz-fields [data-f]").forEach(i => { f[i.dataset.f] = i.value.trim() || SAMPLE[i.dataset.f] || ""; });
  return f;
}
async function render() {
  if (!tpl) return;
  const { lab, DW, DH, r, toPx } = dims(), c = $("#dz-canvas");
  c.width = DW; c.height = DH;
  const ctx = c.getContext("2d");
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, DW, DH);
  await templateImagesReady(tpl);
  try { drawTemplate(ctx, tpl, fields(), DW, DH, { drawBarcode: (cx, d, x, y, w, h, sym) => drawCode(cx, sym, d, x, y, w, h), usDate }); }
  catch (err) { toast(err.message, true); }
  const o = tpl.objects[sel];
  if (o) {
    const x = toPx(o.x, r.x), y = toPx(o.y, r.y), w = toPx(o.w, 0), h = toPx(o.h, 0);
    ctx.save(); ctx.strokeStyle = "#1a73e8"; ctx.lineWidth = 3; ctx.setLineDash([12, 8]); ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]); ctx.fillStyle = "#1a73e8"; ctx.fillRect(x + w - 14, y + h - 14, 18, 18); ctx.restore();
  }
  $("#dz-size").textContent = `${lab.name} · printable ${inches((lab.safe_in[2] - lab.safe_in[0]))}″ × ${inches((lab.safe_in[3] - lab.safe_in[1]))}″ · ` +
    `${lab.printers.map(p => p === "550T" ? "550 Turbo" : "5XL").join(" or ")}${dirty ? " · not saved" : ""}`;
}

// ---- pointer: select, move, resize (corner), arrow keys nudge 0.01″ (Shift: 0.1″)
let drag = null;
function at(e) {
  const c = $("#dz-canvas"), b = c.getBoundingClientRect();
  return [(e.clientX - b.left) * c.width / b.width, (e.clientY - b.top) * c.height / b.height];
}
function hit(px, py) {
  const { r, toPx } = dims();
  for (let i = tpl.objects.length - 1; i >= 0; i--) {
    const o = tpl.objects[i], x = toPx(o.x, r.x), y = toPx(o.y, r.y), w = toPx(o.w, 0), h = toPx(o.h, 0);
    if (px >= x - 6 && px <= x + w + 6 && py >= y - 6 && py <= y + h + 6) return { i, corner: px > x + w - 30 && py > y + h - 30 };
  }
  return null;
}
function wire() {
  const c = $("#dz-canvas");
  c.onpointerdown = e => {
    const [px, py] = at(e), h = hit(px, py);
    select(h ? h.i : -1);
    if (h) { const o = tpl.objects[h.i]; drag = { px, py, o: { ...o }, corner: h.corner }; c.setPointerCapture(e.pointerId); }
  };
  c.onpointermove = e => {
    if (!drag) return;
    const [px, py] = at(e), { s } = dims(), dx = (px - drag.px) / (DPI * s), dy = (py - drag.py) / (DPI * s), o = tpl.objects[sel];
    if (drag.corner) { o.w = inches(Math.max(0.05, drag.o.w + dx)); o.h = inches(Math.max(0.03, drag.o.h + dy)); }
    else { o.x = inches(drag.o.x + dx); o.y = inches(drag.o.y + dy); }
    changed(false);
  };
  c.onpointerup = () => { if (drag) { drag = null; props(); } };
  c.onkeydown = e => {
    const o = tpl.objects[sel];
    if (!o) return;
    const d = e.shiftKey ? 0.1 : 0.01, m = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] }[e.key];
    if (m) { e.preventDefault(); o.x = inches(o.x + m[0]); o.y = inches(o.y + m[1]); changed(); }
    if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); removeSel(); }
  };
}

// ---- the object list and the selected object's properties
const label = o => o.kind === "text" ? `Text: ${o.format.replace(/\n/g, " / ").slice(0, 28)}` : o.kind === "barcode"
  ? `${(CODES.find(c => c[0] === o.symbology) || CODES[0])[1]}: ${o.format}` : o.kind === "image" ? "Picture"
  : { line: "Line", box: "Box", fill: "Filled box" }[o.shape] || "Shape";
function list() {
  $("#dz-objects").innerHTML = tpl.objects.map((o, i) => `<li data-i="${i}" class="${i === sel ? "on" : ""}">${esc(label(o))}</li>`).join("")
    || `<li class="hint">Nothing yet — add text, a field, a barcode…</li>`;
  $$("#dz-objects li[data-i]").forEach(li => li.onclick = () => select(+li.dataset.i));
}
function select(i) { sel = i; list(); props(); render(); }
function field(lbl, html, wide = false) { return `<label class="${wide ? "wide" : ""}">${lbl}${html}</label>`; }
function props() {
  const o = tpl.objects[sel], P = $("#dz-props");
  if (!o) { P.innerHTML = `<p class="hint wide">Click something on the label to change it.</p>`; return; }
  const num = (k, step = 0.01) => `<input type="number" step="${step}" data-k="${k}" value="${o[k]}">`;
  let h = "";
  if (o.kind === "text") {
    const st = o.lines[0];
    h += field("Text <small>(fields fill in when printing)</small>", `<textarea data-k="format">${esc(o.format)}</textarea>`, true);
    h += `<div class="wide chips">${FIELDS.map(([f, n]) => `<button type="button" class="chip" data-ins="${f}">${n}</button>`).join("")}</div>`;
    h += field("Size (pt)", `<input type="number" min="4" max="200" data-st="size" value="${st.size}">`);
    h += field("Bold", `<input type="checkbox" data-st="bold" ${st.bold ? "checked" : ""}>`) + field("Italic", `<input type="checkbox" data-st="italic" ${st.italic ? "checked" : ""}>`);
    h += field("Align", `<select data-k="halign">${["Left", "Center", "Right"].map(a => `<option ${o.halign === a ? "selected" : ""}>${a}</option>`).join("")}</select>`);
    h += field("Shrink to fit", `<input type="checkbox" data-fit ${o.fit !== "None" ? "checked" : ""}>`);
  }
  if (o.kind === "barcode") {
    h += field("Type", `<select data-k="symbology">${CODES.map(([v, n]) => `<option value="${v}" ${o.symbology === v ? "selected" : ""}>${n}</option>`).join("")}</select>`);
    h += field("Data <small>(e.g. {ticket})</small>", `<input data-k="format" value="${esc(o.format)}">`, true);
    if (o.symbology === "QRCode") h += `<p class="hint wide">QR is for customers' phones — the shop's scanner reads 1D barcodes only.</p>`;
  }
  if (o.kind === "image") h += `<button type="button" class="ghost wide" id="dz-repic">Choose another picture…</button>`;
  if (o.kind === "shape") {
    h += field("Shape", `<select data-k="shape">${[["line", "Line"], ["box", "Box"], ["fill", "Filled box"]].map(([v, n]) => `<option value="${v}" ${o.shape === v ? "selected" : ""}>${n}</option>`).join("")}</select>`);
    h += field("Thickness (in)", num("stroke", 0.005));
  }
  h += field("Left (in)", num("x")) + field("Top (in)", num("y")) + field("Width (in)", num("w")) + field("Height (in)", num("h"));
  h += `<div class="wide row actions"><button type="button" class="ghost" id="dz-up">Bring forward</button><button type="button" class="ghost" id="dz-down">Send back</button>` +
       `<button type="button" class="ghost" id="dz-dup">Duplicate</button><button type="button" class="ghost" id="dz-rm">Remove</button></div>`;
  P.innerHTML = h;
  $$("[data-k]", P).forEach(el => el.oninput = () => {
    o[el.dataset.k] = el.type === "number" ? inches(+el.value) : el.value;
    if (el.dataset.k === "format") o.sample = o.format;
    if (el.dataset.k === "symbology") props();
    changed();
  });
  $$("[data-st]", P).forEach(el => el.oninput = () => { o.lines[0][el.dataset.st] = el.type === "checkbox" ? el.checked : +el.value; changed(); });
  $$("[data-fit]", P).forEach(el => el.oninput = () => { o.fit = el.checked ? "ShrinkToFit" : "None"; changed(); });
  $$("[data-ins]", P).forEach(b => b.onclick = () => { const t = $("[data-k=format]", P); t.value += (t.value && !/\s$/.test(t.value) ? " " : "") + b.dataset.ins; t.oninput(); });
  $("#dz-up", P).onclick = () => move(1); $("#dz-down", P).onclick = () => move(-1);
  $("#dz-rm", P).onclick = removeSel;
  $("#dz-dup", P).onclick = () => { tpl.objects.push({ ...structuredClone(o), x: inches(o.x + 0.05), y: inches(o.y + 0.05) }); select(tpl.objects.length - 1); changed(); };
  if ($("#dz-repic", P)) $("#dz-repic", P).onclick = () => pickPicture(o);
}
function move(d) {
  const j = sel + d;
  if (j < 0 || j >= tpl.objects.length) return;
  [tpl.objects[sel], tpl.objects[j]] = [tpl.objects[j], tpl.objects[sel]];
  select(j); changed();
}
function removeSel() { if (sel < 0) return; tpl.objects.splice(sel, 1); sel = -1; list(); props(); changed(); }
function changed(full = true) { dirty = true; if (full) list(); render(); }

// ---- adding things
function add(kind) {
  const { DW, DH, r, s } = dims(), w = DW / (DPI * s), h = DH / (DPI * s), cx = r.x + w * 0.1, cy = r.y + h * 0.1;
  let o;
  if (kind === "text") o = text("Text", cx, cy, w * 0.6, h * 0.25, 14);
  if (kind === "field") o = text("{company}", cx, cy, w * 0.7, h * 0.25, 16, true);
  if (kind === "barcode") o = { kind: "barcode", name: "Barcode", x: cx, y: cy, w: w * 0.7, h: h * 0.3, halign: "Left", format: "{ticket}", symbology: "Code128Auto" };
  if (kind === "qr") { const q = Math.min(w, h) * 0.6; o = { kind: "barcode", name: "QR", x: cx, y: cy, w: q, h: q, halign: "Left", format: "https://", symbology: "QRCode" }; }
  if (kind === "line") o = { kind: "shape", shape: "line", x: cx, y: cy, w: w * 0.8, h: 0.05, stroke: 0.02 };
  if (kind === "box") o = { kind: "shape", shape: "box", x: cx, y: cy, w: w * 0.5, h: h * 0.5, stroke: 0.02 };
  if (kind === "image") return pickPicture(null);
  for (const k of ["x", "y", "w", "h"]) o[k] = inches(o[k]);
  tpl.objects.push(o); select(tpl.objects.length - 1); changed();
}
let picFor = null;
function pickPicture(o) { picFor = o; $("#dz-picture").click(); }
$("#dz-picture").onchange = async e => {
  const f = e.target.files[0]; e.target.value = "";
  if (!f) return;
  const src = await new Promise(ok => { const r = new FileReader(); r.onload = () => ok(r.result); r.readAsDataURL(f); });
  if (picFor) { picFor.src = src; changed(); return; }
  const { DW, DH, r, s } = dims(), q = Math.min(DW, DH) / (DPI * s) * 0.5;
  tpl.objects.push({ kind: "image", name: "Picture", x: inches(r.x + 0.05), y: inches(r.y + 0.05), w: inches(q), h: inches(q), halign: "Center", scale: "Uniform", src, format: "", sample: "(picture)" });
  select(tpl.objects.length - 1); changed();
};

// ---- layouts: mine (this PC), the shop's (templates/ in the repo), new
function layouts() {
  const mine = loadTemplates();
  $("#dz-open").innerHTML = `<option value="new">＋ New layout</option>` +
    (mine.length ? `<optgroup label="On this PC">${mine.map(t => `<option value="${esc(t.id)}">${esc(t.name)}</option>`).join("")}</optgroup>` : "") +
    (SHOP.length ? `<optgroup label="The shop's">${SHOP.map(t => `<option value="${esc(t.id)}">${esc(t.name)}</option>`).join("")}</optgroup>` : "");
  $("#dz-open").value = tpl?.id && [...mine, ...SHOP].some(t => t.id === tpl.id) ? tpl.id : "new";
}
function open(t) {
  tpl = structuredClone(t);
  if (!tpl.stock) {                                                      // an imported .dymo: guess the label from its name
    const sku = (String(tpl.labelName || "").match(/\d{5,7}/) || [])[0];
    tpl.stock = (STOCKS.find(s => s.sku === sku) || stockOf("w79h252")).id;
  }
  tpl.orientation ||= "Landscape";
  sel = -1; dirty = false;
  $("#dz-name").value = tpl.name; $("#dz-stock").value = tpl.stock; $("#dz-orient").value = tpl.orientation; $("#dz-flip").checked = !!tpl.flip;
  printers(); list(); props(); layouts(); render();
}
function printers() {
  const s = stockOf(tpl.stock);
  $$("#dz-printer option").forEach(o => { o.disabled = !s.printers.includes(o.value === "tag" ? "550T" : "5XL"); });
  if ($("#dz-printer").selectedOptions[0]?.disabled) $("#dz-printer").value = s.printers.includes("550T") ? "tag" : "ship";
  $("#dz-tag").disabled = !isTagLayout(tpl);
}
function stocks() {
  const groups = { "550T": [], "5XL": [] };
  for (const s of STOCKS) (s.printers.includes("550T") ? groups["550T"] : groups["5XL"]).push(s);
  $("#dz-stock").innerHTML = `<optgroup label="550 Turbo (and 5XL)">${groups["550T"].map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("")}</optgroup>` +
    `<optgroup label="5XL only">${groups["5XL"].map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("")}</optgroup>`;
}
function relayout() {                                                    // a new label size or direction: keep objects in proportion
  const old = tpl.rect, { DW, DH } = dims(), w = DW / DPI, h = DH / DPI;
  if (old && old.w && old.h) {
    const kx = w / old.w, ky = h / old.h;
    for (const o of tpl.objects) { o.x = inches((o.x - old.x) * kx); o.y = inches((o.y - old.y) * ky); o.w = inches(o.w * kx); o.h = inches(o.h * ky); }
  }
  tpl.rect = { x: 0, y: 0, w, h };
}

$("#dz-open").onchange = e => {
  if (dirty && !confirm("Leave this layout without saving it?")) { layouts(); return; }
  const id = e.target.value;
  open(id === "new" ? fresh(tpl?.stock) : [...loadTemplates(), ...SHOP].find(t => t.id === id));
};
$("#dz-name").oninput = e => { tpl.name = e.target.value; dirty = true; render(); };
$("#dz-stock").onchange = e => { tpl.stock = e.target.value; relayout(); printers(); changed(); };
$("#dz-orient").onchange = e => { tpl.orientation = e.target.value; relayout(); changed(); };
$("#dz-flip").onchange = e => { tpl.flip = e.target.checked; changed(); };
$$("#dz-add [data-add]").forEach(b => b.onclick = () => add(b.dataset.add));
$$(".dz-fields [data-f]").forEach(i => i.oninput = () => render());

$("#dz-save").onclick = () => {
  const t = structuredClone(tpl);
  if (t.shared) { t.id = `d${Date.now()}`; delete t.shared; t.name += " (my copy)"; }      // the shop's: save a copy
  t.name = t.name.trim() || "Layout";
  const list = loadTemplates().filter(x => x.id !== t.id);
  list.push(t); saveTemplates(list);
  tpl = t; dirty = false; $("#dz-name").value = t.name; layouts(); render();
  toast(`Saved “${t.name}” on this PC`);
};
$("#dz-delete").onclick = () => {
  if (tpl.shared) return toast("That's the shop's layout — the owner removes those", true);
  if (!loadTemplates().some(t => t.id === tpl.id)) return open(fresh(tpl.stock));
  if (!confirm(`Delete “${tpl.name}” from this PC?`)) return;
  saveTemplates(loadTemplates().filter(t => t.id !== tpl.id)); open(fresh(tpl.stock));
};
$("#dz-tag").onclick = () => {
  $("#dz-save").click();
  setActiveTemplate(tpl.id);
  toast(`Inventory tags now use “${tpl.name}” (Inventory tag → Layout to switch back)`);
  document.dispatchEvent(new CustomEvent("labeldesk:templates"));
};
$("#dz-export").onclick = () => {
  const blob = new Blob([JSON.stringify({ ...tpl, id: undefined, shared: undefined }, null, 1)], { type: "application/json" });
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `${(tpl.name || "layout").replace(/[^\w.-]+/g, "-")}.json` });
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
$("#dz-import-btn").onclick = () => $("#dz-import").click();
$("#dz-import").onchange = async e => {
  const f = e.target.files[0]; e.target.value = "";
  if (!f) return;
  try {
    const textData = await f.text();
    const t = /\.dymo$/i.test(f.name) ? parseDymo(textData, f.name) : JSON.parse(textData);
    if (!Array.isArray(t.objects)) throw new Error("not a LabelDesk layout");
    open({ ...t, id: `d${Date.now()}` }); dirty = true; render();
    toast(`Opened “${t.name}” — Save to keep it`);
  } catch (err) { toast(err.message, true); }
};
$("#dz-share").onclick = async () => {
  if (tpl.objects.some(o => o.kind === "image")) return toast("Layouts with pictures can't be shared — the repo is public (logos stay on each PC)", true);
  if (!confirm(`Send “${tpl.name}” to the owner for every PC? It goes in as a pull request when you next run Update.`)) return;
  try {
    const r = await api("templates/share", { template: tpl });
    toast(`Saved as ${r.path} — run tools/update.sh (or ask Claude Code to update LabelDesk) to send it to the owner`);
  } catch (err) { toast(err.message, true); }
};

// ---- print it on its label
$("#dz-print").onclick = async () => {
  for (const o of tpl.objects.filter(o => o.kind === "barcode")) {            // a barcode that can't be made: say so first
    const d = o.format.replace(/\{(\w+)\}/g, (m, k) => ({ company: fields().customer, customer: fields().contact }[k] ?? fields()[k] ?? m));
    try { encode(symbologyOf(o.symbology), d.trim()); } catch (err) { return toast(`${label(o)}: ${err.message}`, true); }
  }
  const lab = labOf(stockOf(tpl.stock));
  await templateImagesReady(tpl);
  const canvas = drawLabel(document.createElement("canvas"), lab, tpl, fields());
  await printCanvas($("#dz-printer").value, canvas, +$("#dz-copies").value || 1, { ...fields(), layout: tpl.name }, `${tpl.name} (${lab.name})`, { stock: tpl.stock });
};

// ---- start
(async () => {
  try { STOCKS = (await api("stocks")).stocks; } catch { return; }
  try { SHOP = (await api("templates/shared")).templates; } catch { SHOP = []; }
  stocks(); wire();
  open(fresh());
  $(".dz-fields [data-f=received]").value = SAMPLE.received;
})();
