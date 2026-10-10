// LabelDesk front end: draws labels at 300 dpi on a canvas (the preview IS the print), prints via the local server.
import { detectLabel } from "./detect.js";
import { draw as drawCode } from "./barcodes.js";
import { parseDymo, drawTemplate, loadTemplates, saveTemplates, activeTemplate, activeTemplateId, setActiveTemplate, templateImagesReady } from "./template.js";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const DPI = 300;
let CFG = null;

async function api(path, body) {
  const r = await fetch("/api/" + path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(d.error || r.statusText), { status: r.status, data: d });
  return d;
}
let toastT;
function toast(msg, bad = false) {
  const t = $("#toast"); t.textContent = msg; t.className = bad ? "bad" : ""; t.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(() => t.hidden = true, bad ? 7000 : 3000);
}
const px = inches => Math.round(inches * DPI);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
// The canvas is the label's PRINTABLE area (from the PPD's ImageableArea), 1 px short so it can never spill:
// CUPS places a 300 ppi image 1:1 there. A full-label image is bigger than that area and CUPS tiles it over 4 pages.
const area = L => [Math.floor((L.safe_in[2] - L.safe_in[0]) * DPI) - 1, Math.floor((L.safe_in[3] - L.safe_in[1]) * DPI) - 1];

// ------------------------------------------------------------------ barcodes (web/barcodes.js): Code 128, Code 39, UPC-A, EAN-13, QR
export { C128, code128 } from "./barcodes.js";
// the tag's ticket barcode: Code 128 (default) or Code 39, Settings → Tag barcode — both read by the shop's 1D scanner
const tagSymbology = () => (CFG && CFG.tagBarcode) || "code128";
function drawBarcode(ctx, text, x, y, w, h, symbology = tagSymbology()) {
  drawCode(ctx, symbology, text, x, y, w, h);
}

// ------------------------------------------------------------------ text fitting
function fit(ctx, text, maxW, size, min, weight = "700") {
  for (let s = size; s >= min; s -= 2) {
    ctx.font = `${weight} ${s}px "DejaVu Sans", "Liberation Sans", Arial, sans-serif`;
    if (ctx.measureText(text).width <= maxW) return s;
  }
  return min;
}
const usDate = iso => { const [y, m, d] = (iso || "").split("-"); return y ? `${m}/${d}/${y}` : ""; };
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

// ------------------------------------------------------------------ inventory tag (30252 or 30321), drawn across the label's length
// shop logo, bottom right of the built-in tag, drawn 0.42" tall on 30321 (scaled with the label's height). It's per PC (Settings → Tag logo, kept in the config
// folder), never in the repo; no logo → the tag is drawn without one.
let TAG_LOGO = new Image();
function loadLogo() {
  const img = new Image(); bwLogo = null;
  img.src = "api/logo?" + Date.now();
  return img.decode().then(() => { TAG_LOGO = img; }, () => { TAG_LOGO = new Image(); });
}
export let tagLogoReady = Promise.resolve();
const LOGO_H = px(0.42);
// the logo at print size in pure black and white (the colour face/lenses → white), drawn 1:1 so it stays crisp
let bwLogo = null;
function tagLogo(height = LOGO_H) {
  if (!TAG_LOGO.complete || !TAG_LOGO.naturalWidth) return null;
  if (bwLogo && bwLogo.height === height) return bwLogo;
  const c = document.createElement("canvas");
  c.height = height; c.width = Math.round(height * TAG_LOGO.naturalWidth / TAG_LOGO.naturalHeight);
  const ctx = c.getContext("2d");
  ctx.imageSmoothingQuality = "high"; ctx.drawImage(TAG_LOGO, 0, 0, c.width, c.height);
  const img = ctx.getImageData(0, 0, c.width, c.height), d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const lum = (0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]) * d[i + 3] / 255 + 255 - d[i + 3];
    d[i] = d[i + 1] = d[i + 2] = lum < 128 ? 0 : 255; d[i + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  return bwLogo = c;
}
// offsetMm: the whole design (text, barcode, logo) moves down (+) / up (−) — fixes printers that clip the top line
export function drawTag(canvas, f, flip = false, offsetMm = tagOffset(), tpl = activeTemplate()) {
  const [W, H] = area(CFG.labels.tag);                        // printable area as fed: 30321 391 × 960, 30252 298 × 962
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, W, H);
  ctx.save();                                                   // design across the label's length, turned onto the page
  if (!flip) { ctx.translate(W, 0); ctx.rotate(Math.PI / 2); } else { ctx.translate(0, H); ctx.rotate(-Math.PI / 2); }
  const DW = H, DH = W;                                         // design space: 960 × 391 (30321) or 962 × 298 (30252)
  const k = Math.min(1, DH / 391), z = v => Math.round(v * k);  // sizes below are for 30321; narrower labels scale down
  if (f.free != null) {                                         // blank tag: just the typed lines (offset + flip apply)
    ctx.translate(0, Math.round(offsetMm / 25.4 * 300));
    drawFree(ctx, f.free, DW, DH);
    ctx.restore();
    return canvas;
  }
  if (tpl) {                                                    // imported .dymo layout (template.js); offset + flip still apply
    ctx.translate(0, Math.round(offsetMm / 25.4 * 300));
    drawTemplate(ctx, tpl, f, DW, DH, { drawBarcode, usDate });
    ctx.restore();
    return canvas;
  }
  ctx.translate(0, Math.round(offsetMm / 25.4 * 300));
  const left = 16, right = DW - 16, top = 10, bottom = DH - 10;
  const w = right - left;
  ctx.fillStyle = "#000"; ctx.textBaseline = "alphabetic";
  const bar = f.barcode && f.ticket;
  const name = f.customer || "Customer";
  // a long customer name: one line down to 56 px, else two lines (split at the space nearest the middle)
  let nameLines = [name], nameMax = z(bar ? 88 : 104);
  if (fit(ctx, name, w, nameMax, z(56)) === z(56) && ctx.measureText(name).width > w && name.includes(" ")) {
    const spaces = [...name.matchAll(/ /g)].map(m => m.index);
    const cut = spaces.reduce((a, b) => Math.abs(b - name.length / 2) < Math.abs(a - name.length / 2) ? b : a);
    nameLines = [name.slice(0, cut), name.slice(cut + 1)];
    nameMax = z(bar ? 52 : 62);
  }
  // intake details on one small line: S/N (scanned) and shelf/bin; an accessory tag says what it is and "2 of 3"
  const intake = [f.serial ? `S/N ${f.serial}` : "", f.bin ? `Bin ${f.bin}` : ""].filter(Boolean).join("   ");
  const item = f.item ? `${f.item}${f.part ? ` · ${f.part}` : ""}` : (f.part ? `Device · ${f.part}` : "");
  const extra = [item && { t: item, size: z(bar ? 50 : 60), min: z(28), weight: "700" },
                 intake && { t: intake, size: z(bar ? 40 : 48), min: z(24), weight: "400" }].filter(Boolean);
  const small = !!f.contact || nameLines.length > 1 || extra.length > 0;   // a 4th line: everything a little smaller
  const lines = [
    ...nameLines.map(t => ({ t, size: small ? Math.min(nameMax, z(78)) : nameMax, min: z(30), weight: "700", name: true })),
    ...(f.contact ? [{ t: f.contact, size: z(bar ? 44 : 54), min: z(28), weight: "400" }] : []),
    ...extra,
    { t: `Received: ${usDate(f.received)}`, size: z(small ? (bar ? 42 : 50) : (bar ? 54 : 62)), min: z(28), weight: "400" },
    { t: `Ticket#: ${f.ticket || ""}`, size: z(small ? (bar ? 56 : 68) : (bar ? 70 : 88)), min: z(32), weight: "700" },
  ];
  if (nameLines.length > 1) {                                   // both name lines the same size
    const s = Math.min(...nameLines.map(t => fit(ctx, t, w, nameMax, z(30))));
    lines[0].size = lines[1].size = s;
  }
  const barH = bar ? z(small ? 56 : 70) : 0, gap = z(small ? 8 : 14);
  const logoH = z(LOGO_H), logo = tagLogo(logoH);
  const logoW = logo ? logo.width : 0, logoY = bottom - logoH;
  const narrow = w - logoW - 24;                                // lines that reach down beside the logo stop short of it
  let maxW = lines.map(() => w), sizes, ys, barY;
  for (let pass = 0; pass < 4; pass++) {
    sizes = lines.map((l, i) => fit(ctx, l.t, maxW[i], l.size, l.min, l.weight));
    const total = sizes.reduce((s, x) => s + x, 0) + gap * (lines.length - 1) + (bar ? barH + gap : 0);
    let y = top + Math.max(0, (bottom - top - total) / 2);
    ys = lines.map((l, i) => {
      const base = y + sizes[i] * 0.86;
      y = base + sizes[i] * 0.14 + (l.name && nameLines.length > 1 && i === 0 ? z(4) : gap);
      return base;
    });
    barY = y;
    const next = lines.map((l, i) => logo && ys[i] + sizes[i] * 0.14 > logoY ? narrow : maxW[i]);
    if (next.every((v, i) => v === maxW[i])) break;
    maxW = next;
  }
  lines.forEach((l, i) => {
    ctx.font = `${l.weight} ${sizes[i]}px "DejaVu Sans", "Liberation Sans", Arial, sans-serif`;
    ctx.globalAlpha = f.customer || !l.name ? 1 : .25;
    const tw = ctx.measureText(l.t).width;                    // still too long at the smallest size: condense it
    if (tw > maxW[i]) { ctx.save(); ctx.translate(left, ys[i]); ctx.scale(maxW[i] / tw, 1); ctx.fillText(l.t, 0, 0); ctx.restore(); }
    else ctx.fillText(l.t, left, ys[i]);
  });
  ctx.globalAlpha = 1;
  if (bar) drawBarcode(ctx, String(f.ticket), left, barY, logo ? narrow : w, barH);
  if (logo) ctx.drawImage(logo, right - logoW, logoY);
  ctx.restore();
  return canvas;
}

// blank tag: each typed line as big as it can be (same size for all lines), centred on the label
function drawFree(ctx, text, DW, DH) {
  const lines = String(text).replace(/\s+$/, "").split("\n");
  const left = 16, w = DW - 32, top = 10, h = DH - 20, gap = 0.18;
  ctx.fillStyle = "#000"; ctx.textBaseline = "alphabetic"; ctx.textAlign = "center";
  if (!lines.join("").trim()) { ctx.globalAlpha = .25; lines.splice(0, lines.length, "Type your text"); }
  let size = Math.min(160, h / (lines.length * (1 + gap)));
  for (; size > 14; size -= 2) {
    ctx.font = `700 ${size}px "DejaVu Sans", "Liberation Sans", Arial, sans-serif`;
    if (lines.every(t => ctx.measureText(t).width <= w)) break;
  }
  const lh = size * (1 + gap), total = lh * lines.length - size * gap;
  let y = top + (h - total) / 2;
  lines.forEach(t => {
    y += size * 0.86;
    const tw = ctx.measureText(t).width;
    if (tw > w) { ctx.save(); ctx.translate(left + w / 2, y); ctx.scale(w / tw, 1); ctx.fillText(t, 0, 0); ctx.restore(); }
    else ctx.fillText(t, left + w / 2, y);
    y += size * 0.14 + size * gap;
  });
  ctx.textAlign = "left"; ctx.globalAlpha = 1;
}

// ------------------------------------------------------------------ printing
// ---- the job bar: every print is followed until the printer has finished (server asks CUPS) — "sent" isn't "printed"
const PRINTER_NAME = { tag: "550 Turbo", ship: "5XL" };
let busy = false, forceUntil = 0;
function jobbar(msg, kind = "", actions = []) {
  const bar = $("#jobbar");
  bar.className = kind; bar.hidden = !msg;
  $(".msg", bar).textContent = msg || "";
  $(".acts", bar).replaceChildren(...actions.map(([label, fn]) => {
    const b = document.createElement("button"); b.textContent = label; b.onclick = fn; return b; }));
  clearTimeout(jobbar.t);
  if (kind === "ok") jobbar.t = setTimeout(() => bar.hidden = true, 6000);
}
async function track(id, what, kind, retry) {
  for (let i = 0; i < 120; i++) {
    let s;
    try { s = await api("job/" + id); } catch { await new Promise(r => setTimeout(r, 1000)); continue; }
    if (s.state === "done") { jobbar(`✓ Printed: ${what}`, "ok"); loadPrinters(); return true; }
    if (s.state === "failed") {
      const p = await api("printers").catch(() => ({}));
      const acts = [["Print again", retry]];
      if (p[kind]?.paused) acts.unshift(["Resume printer", async () => { await api(`printers/${kind}/resume`, {}); loadPrinters(); retry(); }]);
      jobbar(`✗ Not printed (${PRINTER_NAME[kind]}): ${s.message}`, "bad", acts); loadPrinters(); return false;
    }
    jobbar(`${PRINTER_NAME[kind]}: ${s.message || "printing…"} — ${what}`, "wait", [["Cancel", async () => {
      try { await api(`job/${id}/cancel`, {}); } catch (err) { toast(err.message, true); } }]]);
    await new Promise(r => setTimeout(r, 1000));
  }
  jobbar(`${PRINTER_NAME[kind]} hasn't finished "${what}" after 2 minutes — check the printer`, "bad");
  return false;
}
// Windows + Mac: the label as 8-bit grey pixels (Windows: straight to the DYMO driver; Mac: an exact-size PDF — no PNG decoding)
function grayOf(canvas) {
  const { width: w, height: h } = canvas, d = canvas.getContext("2d").getImageData(0, 0, w, h).data;
  const g = new Uint8Array(w * h);
  for (let i = 0, j = 0; j < g.length; i += 4, j++) g[j] = (d[i] * 299 + d[i + 1] * 587 + d[i + 2] * 114) / 1000;
  let s = ""; for (let i = 0; i < g.length; i += 0x8000) s += String.fromCharCode.apply(null, g.subarray(i, i + 0x8000));
  return { w, h, data: btoa(s) };
}
// send one label: resolves when CUPS has it (the bar keeps following it). Double press within 3 s → asks first;
// a shipping label whose barcode can't be read → "Print anyway" instead of printing a label that won't scan.
async function printCanvas(kind, canvas, copies, fields, what, { force = false, wait = false } = {}) {
  if (busy) return false;
  if (copies > 10 && !confirm(`Print ${copies} copies?`)) return false;
  busy = true; $$("button.primary").forEach(b => b.disabled = true);
  const png = canvas.toDataURL("image/png");
  const again = () => printCanvas(kind, canvas, copies, fields, what, { force: true });
  try {
    let check;
    if (kind === "ship" && !CFG.barcodeCheck) {                // no zbar on this PC (Windows): check in the browser
      jobbar("Checking the barcode…", "wait");
      check = await checkBarcode(canvas);
      if (!check.ok && !force) {
        jobbar(`⚠ ${check.message}`, "bad", [["Print anyway", again], ["Cancel", () => jobbar("")]]);
        return false;
      }
    }
    const gray = CFG.platform === "windows" || CFG.platform === "mac" ? grayOf(canvas) : undefined;
    jobbar(`Sending to the ${PRINTER_NAME[kind]}… — ${what}`, "wait");
    const r = await api("print", { kind, png, gray, check, copies, fields, force: force || Date.now() < forceUntil });
    const label = r.check?.tracking ? `${what} · ${r.check.carrier} ${r.check.tracking}` : what;
    const done = track(r.id, label, kind, again);
    done.then(ok => { if (ok) checkUpdate(); });                // after every print: is there a newer LabelDesk?
    return wait ? await done : true;
  } catch (err) {
    if (err.status === 409) { forceUntil = Date.now() + 5000; jobbar("Just sent that one — press Print again within 5 s to print another copy", "wait"); }
    else if (err.status === 422) jobbar(`⚠ ${err.message}`, "bad", [["Print anyway", again], ["Cancel", () => jobbar("")]]);
    else jobbar(`✗ Not printed: ${err.message}`, "bad", [["Try again", again]]);
    return false;
  } finally { busy = false; $$("button.primary").forEach(b => b.disabled = false); $("#ship-print").disabled = !SHIP.src; }
}

// ---- new version? asked after every successful print (the server caches GitHub's answer for a minute)
let updateHidden = "";
async function checkUpdate() {
  let u;
  try { u = await api("update"); } catch { return; }
  $("#about-update").textContent = u.held ? `This PC is held at version ${u.held} (Settings → Version).`
    : !u.enabled ? "Update check is off (config.json update_check)."
    : u.error ? `Couldn't check for updates (${u.error}).`
    : u.newer ? `Version ${u.latest} is available.` : `Up to date (checked after the last print).`;
  const bar = $("#updatebar");
  if (u.held || !u.enabled || !u.newer || updateHidden === u.latest) { bar.hidden = true; return; }
  const msg = $(".msg", bar), acts = $(".acts", bar);
  const later = document.createElement("button"); later.textContent = "Later";
  later.onclick = () => { updateHidden = u.latest; bar.hidden = true; };
  if (u.how === "git" && u.canUpdateNow) {
    msg.textContent = `LabelDesk ${u.latest} is available (this PC has ${u.current}).`;
    const now = document.createElement("button"); now.textContent = "Update now";
    now.onclick = () => runUpdate("update/run", {}, u, msg, acts);
    acts.replaceChildren(now, later);
  } else if (u.how === "git") {
    msg.innerHTML = `LabelDesk ${esc(u.latest)} is available (this PC has ${esc(u.current)}). This PC has its own changes (sent to the
      owner for approval), so it updates in a Terminal: <code>${esc(u.command)}</code>`;
    const copy = document.createElement("button"); copy.textContent = "Copy command";
    copy.onclick = async () => { try { await navigator.clipboard.writeText(u.command); toast("Copied"); } catch { toast("Select the command and copy it", true); } };
    acts.replaceChildren(copy, later);
  } else if (u.how === "windows") {
    msg.textContent = `LabelDesk ${u.latest} is available (this PC has ${u.current}).`;
    const inst = document.createElement("button"); inst.textContent = "Install update";
    inst.onclick = () => runUpdate("update/install", { version: u.latest }, u, msg, acts);
    const open = document.createElement("button"); open.textContent = "Releases page";
    open.onclick = () => window.open(u.releases, "_blank", "noopener");
    acts.replaceChildren(inst, open, later);
  } else {
    msg.innerHTML = u.how === "windows"
      ? `LabelDesk ${esc(u.latest)} is available (this PC has ${esc(u.current)}). Get the new installer from the releases page.`
      : `LabelDesk ${esc(u.latest)} is available (this PC has ${esc(u.current)}). This copy isn't a git checkout: reinstall it from GitHub (README, "Install").`;
    const open = document.createElement("button"); open.textContent = "Open releases";
    open.onclick = () => window.open(u.releases, "_blank", "noopener");
    acts.replaceChildren(open, later);
  }
  bar.hidden = false;
}

// start the update, then wait for LabelDesk to come back with the new version and reload the page
async function runUpdate(path, body, u, msg, acts) {
  if (busy) return toast("Wait for the print to finish first", true);
  try { await api(path, body); } catch (err) { return toast(err.message, true); }
  acts.replaceChildren(); msg.textContent = `Updating to ${u.latest}… LabelDesk restarts by itself (about a minute).`;
  for (let i = 0; i < 90; i++) {
    await new Promise(r => setTimeout(r, 2000));
    try { const c = await api("config"); if (c.version !== u.current) return location.reload(); } catch { /* restarting */ }
  }
  let log = ""; try { log = (await api("update/log")).log; } catch {}
  msg.innerHTML = `The update didn't finish. ${u.how === "git" ? `Run <code>${esc(u.command)}</code> in a Terminal to see why.` : "Try the Releases page."}`
    + (log ? `<pre class="updlog">${esc(log.slice(-800))}</pre>` : "");
}

// ---- Settings → Version: any published version on this PC (it stays there), back to the newest, or (owner) for every PC
let VERS = null;
async function loadVersions() {
  try { VERS = await api("versions"); } catch (err) { $("#ver-state").textContent = err.message; return; }
  const v = VERS, newest = v.newest;
  $("#ver-state").textContent = v.error ? `This PC runs ${v.current}. ${v.error}.`
    : v.held ? `This PC is held at ${v.current} — it doesn't take updates until you go back to the newest version (${newest}).`
    : `This PC runs ${v.current}${v.current === newest ? " — the newest version" : newest ? ` (newest: ${newest})` : ""}.`;
  $("#ver-pick").innerHTML = v.versions.map(x =>
    `<option value="${esc(x.version)}" ${x.installable ? "" : "disabled"} ${x.current ? "selected" : ""}>${esc(x.version)} · ${esc(x.date)}` +
    `${x.version === newest ? " · newest" : ""}${x.current ? " · on this PC" : ""}${x.installable ? "" : " · not for this system"}</option>`).join("");
  $("#ver-everyone-row").hidden = !v.publisher;
  $("#ver-newest").hidden = !v.held;
  showVersionNotes();
}
function showVersionNotes() {
  const x = VERS?.versions.find(x => x.version === $("#ver-pick").value);
  $("#ver-notes").innerHTML = x ? x.notes.map(n => `<li>${esc(n.replace(/\*\*/g, ""))}</li>`).join("") : "";
  $("#ver-use").disabled = !x || (x.current && !$("#ver-everyone").checked);
}
$("#ver-pick").onchange = showVersionNotes;
$("#ver-everyone").onchange = showVersionNotes;
async function switchVersion(version, everyone) {
  if (busy) return toast("Wait for the print to finish first", true);
  const what = version === "newest" ? "go back to the newest version"
    : everyone ? `publish version ${version}'s code for EVERY PC (they all go back with their next update)`
    : `put this PC on version ${version} (it stays there until you choose "Back to the newest version")`;
  if (!confirm(`LabelDesk will ${what}, then restart. Go ahead?`)) return;
  try { await api("version/use", { version, everyone }); } catch (err) { return toast(err.message, true); }
  const from = CFG.version;
  if (version === "newest" && VERS.current === VERS.newest && VERS.platform === "windows") {   // nothing to install
    toast("This PC follows updates again"); return loadVersions();
  }
  $("#ver-msg").textContent = "Switching… LabelDesk restarts by itself (about a minute).";
  $("#ver-use").disabled = true;
  for (let i = 0; i < 90; i++) {
    await new Promise(r => setTimeout(r, 2000));
    try { const c = await api("config"); if (c.version !== from || c.started !== CFG.started) return location.reload(); } catch { /* restarting */ }
  }
  let log = ""; try { log = (await api("update/log")).log; } catch {}
  $("#ver-msg").innerHTML = "That didn't finish." + (log ? `<pre class="updlog">${esc(log.slice(-800))}</pre>` : "");
}
$("#ver-use").onclick = () => switchVersion($("#ver-pick").value, $("#ver-everyone").checked);
$("#ver-newest").onclick = () => switchVersion("newest", false);

// ------------------------------------------------------------------ tag form
const form = $("#tag-form");
const tagFields = () => ({ customer: form.customer.value.trim(), received: form.received.value, ticket: form.ticket.value.trim().replace(/^#/, ""),
                           barcode: form.barcode.checked, contact: form.showContact.checked ? form.contact.value.trim() : "",
                           serial: form.serial.value.trim(), bin: form.bin.value.trim() });
// accessories typed or picked: "Charger, Dock" → ["Charger", "Dock"] (each gets its own tag: "2 of 3")
const accessories = () => form.accessories.value.split(/[,;\n]/).map(s => s.trim()).filter(Boolean);
const flip = () => { try { return JSON.parse(localStorage.getItem("flipTag")) ?? CFG.flipTag; } catch { return CFG.flipTag; } };
// text position on the tag (mm, + = down), per PC like Rotate 180°; config.json tag_offset_mm is the default
function tagOffset() {
  try { const v = JSON.parse(localStorage.getItem("tagOffsetMm")); if (typeof v === "number") return v; } catch {}
  return (typeof CFG !== "undefined" && CFG && CFG.tagOffsetMm) || 0;
}
const showOffset = () => { const v = tagOffset(); $("#offset-val").textContent = (v > 0 ? "+" : "") + v.toFixed(2) + " mm"; };
const nudge = d => {
  const v = Math.max(-3, Math.min(3, Math.round((tagOffset() + d) * 4) / 4));
  try { localStorage.setItem("tagOffsetMm", JSON.stringify(v)); } catch {}
  showOffset(); drawTagPreview();
};
$("#offset-down").onclick = () => nudge(0.25);
$("#offset-up").onclick = () => nudge(-0.25);
// ---- tag layout: built-in or an imported DYMO Connect template (.dymo), per PC
const tplPanel = $("#tpl-panel");
function showTemplates() {
  const list = loadTemplates(), id = activeTemplateId();
  $("#tpl-select").innerHTML = `<option value="">Built-in</option>` + list.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join("");
  $("#tpl-select").value = list.some(t => t.id === id) ? id : "";
  $("#tpl-edit").hidden = $("#tpl-delete").hidden = !$("#tpl-select").value;
}
function editTemplate(t) {
  const [aw, ah] = area(CFG.labels.tag);
  const big = Math.abs(t.rect?.w * 300 - ah) > 150 || Math.abs(t.rect?.h * 300 - aw) > 80;
  tplPanel.innerHTML = `<h3>Template fields <small>${esc(t.name)}${t.labelName ? " · " + esc(t.labelName) : ""}</small></h3>
    ${t.orientation !== "Landscape" ? `<p class="warn">This template is ${esc(t.orientation)} — LabelDesk draws tags landscape; check the preview.</p>` : ""}
    ${big ? `<p class="warn">Made for a different label size — positions are scaled to this tag. Check the preview.</p>` : ""}
    <p class="hint">Use <code>{company}</code> <code>{customer}</code> <code>{received}</code> <code>{ticket}</code> where the form's values go; anything else prints as typed.</p>
    ${t.objects.map((o, i) => o.kind === "image" ? `<p class="hint">Picture “${esc(o.name || "")}” — printed as it is in the template.</p>`
      : `<label>${o.kind === "barcode" ? "Barcode" : "Text"} “${esc((o.name || "") + "")}” <small>sample: ${esc(o.sample.slice(0, 40))}</small>
      <input data-i="${i}" value="${esc(o.format)}"></label>`).join("")}
    <div class="row actions"><button type="button" class="primary" id="tpl-save">Save</button>
      <button type="button" class="ghost" id="tpl-close">Close</button></div>`;
  tplPanel.hidden = false;
  tplPanel.oninput = e => { const i = e.target.dataset.i; if (i != null) { t.objects[+i].format = e.target.value; drawTagPreview(t); } };
  $("#tpl-save").onclick = () => { const list = loadTemplates().filter(x => x.id !== t.id); saveTemplates([...list, t]);
    setActiveTemplate(t.id); tplPanel.hidden = true; showTemplates(); drawTagPreview(); };
  $("#tpl-close").onclick = () => { tplPanel.hidden = true; drawTagPreview(); };
  drawTagPreview(t);
}
async function importTemplate(file) {
  try { const t = parseDymo(await file.text(), file.name); editTemplate(t); templateImagesReady(t).then(() => drawTagPreview(t)); }
  catch (err) { alert(`Couldn't import ${file.name}: ${err.message}`); }
}
$("#tpl-import").onclick = () => $("#tpl-file").click();
$("#tpl-file").onchange = e => { const f = e.target.files[0]; if (f) importTemplate(f); e.target.value = ""; };
$("#tpl-select").onchange = e => { setActiveTemplate(e.target.value); showTemplates(); drawTagPreview(); templateImagesReady(activeTemplate()).then(() => drawTagPreview()); };
$("#tpl-edit").onclick = () => { const t = activeTemplate(); if (t) editTemplate(structuredClone(t)); };
$("#tpl-delete").onclick = () => { const t = activeTemplate(); if (t && confirm(`Delete the template “${t.name}”?`)) {
  saveTemplates(loadTemplates().filter(x => x.id !== t.id)); setActiveTemplate(""); showTemplates(); drawTagPreview(); } };
const prevCard = $("#tag-canvas").closest(".card");
prevCard.addEventListener("dragover", e => { if ([...e.dataTransfer.items].some(i => i.kind === "file")) e.preventDefault(); });
prevCard.addEventListener("drop", e => { const f = [...e.dataTransfer.files].find(f => /\.dymo$/i.test(f.name)); if (f) { e.preventDefault(); importTemplate(f); } });
$("#offset-reset").onclick = () => { try { localStorage.removeItem("tagOffsetMm"); } catch {} showOffset(); drawTagPreview(); };
// preview in reading orientation (the print image is the same label turned onto the feed direction)
const drawTagPreview = (tpl = activeTemplate()) => {        // tpl: a template being edited (not saved yet)
  const f = FREE.on ? { free: $("#free-text").value } : tagFields();
  const src = drawTag(document.createElement("canvas"), f, false, tagOffset(), tpl), view = $("#tag-canvas");
  view.width = src.height; view.height = src.width;
  const ctx = view.getContext("2d");
  ctx.translate(0, view.height); ctx.rotate(-Math.PI / 2); ctx.drawImage(src, 0, 0);
};
// ---- blank tag: click the preview and type (a technician's idea) — Ctrl+Enter prints, Esc goes back to the ticket tag
const FREE = { on: false };
function freeMode(on) {
  FREE.on = on; $("#free-panel").hidden = !on; $("#tag-canvas").classList.toggle("free", on);
  if (on) $("#free-text").focus(); else form.ticket.focus();
  drawTagPreview();
}
$("#tag-canvas").onclick = () => freeMode(true);
$("#free-text").oninput = () => drawTagPreview();
$("#free-close").onclick = () => freeMode(false);
async function printFree() {
  const text = $("#free-text").value.replace(/\s+$/, "");
  if (!text.trim()) return toast("Type the text for the blank tag first", true);
  const f = { free: text };
  if (await printCanvas("tag", await tagCanvas(f), +form.copies.value || 1, f, tagWhat(f))) {
    try { localStorage.setItem("lastTag", JSON.stringify(f)); } catch {}
  }
}
$("#free-print").onclick = printFree;
$("#free-text").addEventListener("keydown", e => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); printFree(); }
  if (e.key === "Escape") { e.preventDefault(); freeMode(false); }
});
$("#flip").onchange = e => { try { localStorage.setItem("flipTag", e.target.checked); } catch {} drawTagPreview(); };
form.addEventListener("input", () => drawTagPreview());
const tagWhat = f => f.free != null ? `blank tag “${f.free.split("\n")[0].slice(0, 40)}”` : `${f.customer} · #${f.ticket}`;
// the print image for a tag (imported templates' pictures have to be decoded before drawing)
async function tagCanvas(f) {
  if (f.free == null) await templateImagesReady(activeTemplate());
  return drawTag(document.createElement("canvas"), f, flip());
}
form.onsubmit = async e => {
  e.preventDefault();
  if (cwTimer) { clearTimeout(cwTimer); cwTimer = null; cwPending = cwLookup(); }   // Enter faster than the lookup delay
  if (cwPending) { await cwPending; cwPending = null; }
  const f = tagFields();
  if (!f.customer || !f.ticket) return toast("Customer and ticket # are needed", true);
  const acc = accessories(), n = acc.length + 1;
  const device = acc.length ? { ...f, part: `1 of ${n}`, accessories: acc } : f;
  let ok = await printCanvas("tag", await tagCanvas(device), +form.copies.value || 1, device, tagWhat(device), { wait: acc.length > 0 });
  for (let i = 0; ok && i < acc.length; i++) {                 // one tag per accessory, same ticket # and barcode
    const a = { ...f, serial: "", item: acc[i], part: `${i + 2} of ${n}` };
    ok = await printCanvas("tag", await tagCanvas(a), 1, a, `${tagWhat(a)} · ${acc[i]}`, { wait: i < acc.length - 1 });
  }
  if (ok) {
    try { localStorage.setItem("lastTag", JSON.stringify(device)); } catch {}
    form.customer.value = form.ticket.value = form.contact.value = form.serial.value = form.bin.value = form.accessories.value = "";
    cwAuto = { customer: "", contact: "" }; cwInfo(""); cwSeq++;
    form.copies.value = 1; form.ticket.focus(); drawTagPreview(); loadCustomers();
  }
};
// ---- ConnectWise: type the ticket # → Company and Customer name fill in (read-only lookup via the local server).
// Only fields that are empty or were filled by the previous lookup are replaced — typing always wins.
let CW = { configured: false }, cwAuto = { customer: "", contact: "" }, cwTimer, cwSeq = 0, cwPending = null;
function cwInfo(html, kind = "") { const el = $("#cw-info"); el.hidden = !html; el.className = "cwinfo " + kind; el.innerHTML = html || ""; }
async function cwLookup() {
  const n = form.ticket.value.trim().replace(/^#/, "");
  if (!CW.on || !/^\d{3,10}$/.test(n)) return cwInfo("");
  const seq = ++cwSeq;
  cwInfo("Looking up ticket #" + esc(n) + " in ConnectWise…");
  try {
    const t = await api("cw/ticket/" + n);
    if (seq !== cwSeq) return;                                   // a newer keystroke won
    for (const k of ["customer", "contact"]) {
      const val = k === "customer" ? t.company : t.contact;
      if (!form[k].value.trim() || form[k].value === cwAuto[k]) { form[k].value = val; cwAuto[k] = val; }
    }
    cwInfo(`✓ <b>${esc(t.company)}</b>${t.contact ? " · " + esc(t.contact) : ""} <span class="sum">${esc(t.summary)}${t.status ? " · " + esc(t.status) : ""}${t.kind === "project" ? " · project ticket" : ""}</span>`, "ok");
    drawTagPreview();
  } catch (err) {
    if (seq === cwSeq) cwInfo(esc(err.message), err.status === 404 ? "" : "bad");
  }
}
form.ticket.addEventListener("input", () => {
  clearTimeout(cwTimer); cwTimer = setTimeout(() => { cwTimer = null; cwPending = cwLookup(); }, 450);
});
form.showContact.onchange = () => { try { localStorage.setItem("showContact", form.showContact.checked); } catch {} drawTagPreview(); };

// ---- Settings: the ConnectWise keys (kept in this PC's keyring by the server; the private key never comes back)
async function loadCW() {
  try { CW = await api("cw/status"); } catch { CW = { configured: false }; }
  const f = $("#cw-form");
  f.company.value = CW.company || ""; f.client_id.value = CW.clientId || ""; f.public.value = ""; f.private.value = "";
  f.public.placeholder = CW.publicKey ? `stored (${CW.publicKey}) — leave blank to keep` : "";
  f.private.placeholder = CW.configured ? "stored — leave blank to keep" : "";
  $("#cw-state").textContent = CW.on ? `On — connected to company "${CW.company}". Type a ticket # on the tag screen.`
    : CW.configured ? `Keys saved, but ConnectWise isn't answering (${CW.problem}) — lookups stay off until it works.`
    : "Off. LabelDesk works fully without it; with read-only keys from your ConnectWise admin it fills in the company from the ticket #.";
  // ConnectWise stays out of sight unless it's on (or someone opens Settings at #connectwise to set it up)
  $("#cw-card").hidden = !(CW.configured || location.hash === "#connectwise");
  $("#cw-hint").hidden = !CW.on;
  $("#cw-clear").hidden = !CW.configured;
  $("#about-cw").textContent = CW.on ? " — except read-only ticket lookups to your ConnectWise" : "";
  if (!CW.on) cwInfo("");
}
window.addEventListener("hashchange", () => { if (location.hash === "#connectwise") { showTab("settings"); loadCW(); } });
$("#cw-form").onsubmit = async e => {
  e.preventDefault();
  const f = e.target, body = Object.fromEntries(["company", "public", "private", "client_id"].map(k => [k, f[k].value.trim()]));
  try { const r = await api("cw/settings", body); toast(`Saved in the ${r.savedIn}`); await loadCW(); $("#cw-test").click(); }
  catch (err) { toast(err.message, true); }
};
$("#cw-test").onclick = async () => {
  const ul = $("#cw-checks"); ul.innerHTML = "<li>Testing…</li>";
  try {
    const r = await api("cw/test", {});
    ul.innerHTML = `<li class="ok">connected (ConnectWise ${esc(r.version)})</li>` +
      r.checks.map(c => `<li class="${c.ok ? "ok" : "bad"}">${esc(c.what)}: ${esc(c.message)}</li>`).join("");
  } catch (err) { ul.innerHTML = `<li class="bad">${esc(err.message)}</li>`; }
};
$("#win-add-printer").onclick = async () => {
  try { await api("windows/add-printer", {}); toast("Approve the Windows prompt — then 'Shipping Label (LabelDesk)' is in the printer list"); }
  catch (err) { toast(err.message, true); }
};
$("#cw-clear").onclick = async () => {
  if (!confirm("Remove the ConnectWise keys from this PC?")) return;
  await api("cw/clear", {}); $("#cw-checks").innerHTML = ""; await loadCW(); toast("Removed");
};

// ---- Settings → Tag labels: which roll is in the 550 Turbo (the tag is drawn for that label's printable area)
$("#tag-label").onchange = async e => {
  try {
    await api("settings/tag-label", { label: e.target.value });
    CFG = await api("config"); drawTagPreview(); toast(`Tags now print on ${CFG.labels.tag.stock} labels`);
    $("#tag-stock").textContent = `${CFG.tagLabel} · ${CFG.labels.tag.size}`;
  } catch (err) { toast(err.message, true); $("#tag-label").value = CFG.tagLabel; }
};
// ---- Settings → Tag barcode: Code 128 or Code 39 (both read by a 1D scanner)
$("#tag-barcode").onchange = async e => {
  try { await api("settings/tag-barcode", { symbology: e.target.value }); CFG = await api("config"); drawTagPreview(); toast("Saved"); }
  catch (err) { toast(err.message, true); $("#tag-barcode").value = CFG.tagBarcode; }
};
// ---- Settings → Tag logo (per PC; kept in the config folder, not in the app)
function showLogoState() {
  const has = !!TAG_LOGO.naturalWidth;
  $("#logo-state").textContent = has ? "A logo is set on this PC (bottom right of the built-in tag)." : "No logo on this PC: tags print without one.";
  $("#logo-clear").hidden = !has;
}
$("#logo-pick").onclick = () => $("#logo-file").click();
$("#logo-file").onchange = async e => {
  const file = e.target.files[0]; e.target.value = "";
  if (!file) return;
  try {
    const url = await new Promise((ok, bad) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = bad; r.readAsDataURL(file); });
    await api("logo", { png: url }); await loadLogo(); showLogoState(); drawTagPreview(); toast("Logo saved on this PC");
  } catch (err) { toast(err.message, true); }
};
$("#logo-clear").onclick = async () => {
  if (!confirm("Remove the logo from this PC's tags?")) return;
  try { await api("logo/clear", {}); await loadLogo(); showLogoState(); drawTagPreview(); } catch (err) { toast(err.message, true); }
};
// ---- Settings → DYMO printers by IP (Windows): check first (read-only), then add with an admin prompt
const winIps = () => [$("#dymo-ip-550").value.trim(), $("#dymo-ip-5xl").value.trim()].filter(Boolean);
$("#dymo-check").onclick = async () => {
  if (!winIps().length) return toast("Type at least one printer IP", true);
  const out = $("#dymo-out"); out.hidden = false; out.textContent = "Checking (up to a minute)…";
  try { out.textContent = (await api("windows/printer-check", { ips: winIps() })).output; }
  catch (err) { out.textContent = err.message; }
};
for (const [btn, model, input] of [["#dymo-add-550", "550", "#dymo-ip-550"], ["#dymo-add-5xl", "5XL", "#dymo-ip-5xl"]]) {
  $(btn).onclick = async () => {
    const ip = $(input).value.trim();
    if (!ip) return toast("Type that printer's IP first", true);
    try { await api("windows/add-dymo", { model, ip }); toast("Approve the Windows prompt; the window shows the result"); setTimeout(loadPrinters, 8000); }
    catch (err) { toast(err.message, true); }
  };
}

// Print again (Ctrl+R): the last tag, e.g. when one got damaged
async function printLastTag() {
  let f = null; try { f = JSON.parse(localStorage.getItem("lastTag")); } catch {}
  if (!f) return toast("No tag printed yet on this PC", true);
  printCanvas("tag", await tagCanvas(f), 1, f, tagWhat(f) + " (again)", { force: true });
}
$("#tag-again").onclick = printLastTag;
// customer names from past tags → the Customer field suggests them as you type
async function loadCustomers() {
  try { $("#customers").innerHTML = (await api("customers")).customers.map(c => `<option value="${esc(c)}">`).join(""); } catch {}
}
$("#tag-batch-open").onclick = () => { $("#tag-batch").hidden = !$("#tag-batch").hidden; $("#batch-text").focus(); };
$("#batch-print").onclick = async () => {
  const rows = $("#batch-text").value.split("\n").map(l => l.trim()).filter(Boolean).map(l => {
    const i = l.lastIndexOf(","); return i < 0 ? null : { customer: l.slice(0, i).trim(), ticket: l.slice(i + 1).trim().replace(/^#/, "") };
  });
  if (!rows.length || rows.some(r => !r || !r.customer || !r.ticket)) return toast("Each line: Customer, Ticket #", true);
  const st = $("#batch-status");
  for (const [i, r] of rows.entries()) {
    const f = { ...r, received: form.received.value, barcode: form.barcode.checked };
    st.textContent = `Printing ${i + 1} of ${rows.length}…`;
    // each tag waits until the printer has actually printed it — a problem stops the batch where it happened
    if (!await printCanvas("tag", await tagCanvas(f), 1, f, tagWhat(f), { force: true, wait: true })) {
      st.textContent = `Stopped at line ${i + 1} ("${r.customer}") — the lines after it weren't printed.`; return;
    }
  }
  st.textContent = ""; $("#batch-text").value = ""; loadCustomers(); jobbar(`✓ Printed all ${rows.length} tags`, "ok");
};

// ------------------------------------------------------------------ shipping label: paste / drop / open → 4 × 6
// A carrier page (label + instructions + fold line) or a screenshot: detect.js finds the label and which way is up;
// the whole image is shown with the label area outlined — drag to redraw it, ↺ ↻ 180° to turn it.
export const SHIP = { src: null, full: null, crop: null, turn: 0, how: "" };   // full = ImageData for detection
// <img>.decode(), not createImageBitmap(): the latter can hang on big page images (seen in headless Chrome)
async function decodeImage(blob) {
  const img = new Image(), url = URL.createObjectURL(blob);
  try { img.src = url; await img.decode(); } finally { setTimeout(() => URL.revokeObjectURL(url), 1000); }
  return Object.assign(img, { width: img.naturalWidth, height: img.naturalHeight });
}
// ---- PDFs and barcodes in the browser (pdf.js, ZXing) — the same on Fedora and Windows, no extra tools on the PC
let PDFJS = null, BD = null;
async function pdfjs() {
  if (!PDFJS) {
    PDFJS = await import("./vendor/pdf.min.mjs");
    PDFJS.GlobalWorkerOptions.workerSrc = new URL("./vendor/pdf.worker.min.mjs", import.meta.url).href;
  }
  return PDFJS;
}
export async function pdfPage(data, page = 1) {                // → {canvas at 300 dpi, text of the page}
  const lib = await pdfjs();
  const task = lib.getDocument({ data, isEvalSupported: false });
  const doc = await task.promise;
  const p = await doc.getPage(page);
  const vp = p.getViewport({ scale: DPI / 72 });
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(vp.width); canvas.height = Math.round(vp.height);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, canvas.width, canvas.height);
  await p.render({ canvasContext: ctx, viewport: vp }).promise;
  const text = (await p.getTextContent()).items.map(i => i.str).join(" ");
  const pages = doc.numPages;
  task.destroy();                                              // free the worker's copy (many PDFs over a day)
  return { canvas, text, pages };
}
const LABEL_WORDS = /\b(UPS|FedEx|USPS|TRACKING|TRK#|1Z[0-9A-Z]{16}|Ship Manager|Print Your Label)/i;
const CARRIERS = [["UPS", /^(1Z[0-9A-Z]{16})$/, m => m[1]], ["FedEx", /^(?:96|10)\d{20}(\d{12})$/, m => m[1]],
                  ["FedEx", /^(\d{12}|\d{15})$/, m => m[1]], ["USPS", /^(?:420\d{5}(?:\d{4})?)?(9[2-5]\d{18,20})$/, m => m[1]]];
// can a scanner read the tracking barcode on this print image? (the server double-checks with zbar where it has it)
export async function checkBarcode(canvas) {
  try { BD ??= (await import("./vendor/barcode-detector.js")).BarcodeDetector; }
  catch { return { ok: true, message: "barcode check unavailable" }; }
  const found = (await new BD({ formats: ["code_128"] }).detect(canvas)).map(c => c.rawValue.trim());
  for (const c of found) for (const [carrier, rx, t] of CARRIERS) {
    const m = c.match(rx);
    if (m) { const tr = t(m); return { ok: true, carrier, tracking: carrier === "UPS" ? tr : tr.replace(/(\d{4})(?=\d)/g, "$1 "), message: carrier }; }
  }
  return found.length ? { ok: true, carrier: null, tracking: null, message: "a barcode reads, but not as a UPS/FedEx/USPS tracking number" }
    : { ok: false, message: "no barcode could be read — the label may be blurry or cut off. Use the carrier's PDF or zoom in before the screenshot, or check the crop." };
}
export async function loadShip(file, name = file.name || "") {
  SHIP.name = name;
  try {
    let src;
    if (file.type === "application/pdf" || /\.pdf$/i.test(name)) src = (await pdfPage(await file.arrayBuffer())).canvas;
    else if (file.type.startsWith("image/")) src = await decodeImage(file);
    else return toast("That isn't an image or a PDF", true);
    useShipSource(src, name);
  } catch (err) { toast(err.message, true); }
}
function useShipSource(src, name) {                             // an image or a rendered PDF page → detect the label
  SHIP.src = src; SHIP.name = name;
  const c = document.createElement("canvas"); c.width = src.width; c.height = src.height;
  const x = c.getContext("2d", { willReadFrequently: true });
  x.drawImage(src, 0, 0);
  SHIP.full = x.getImageData(0, 0, src.width, src.height);
  findLabel();
}
export function findLabel() {
  const r = detectLabel(SHIP.full);
  if (r) {
    SHIP.crop = r.box; SHIP.how = r.how;
    SHIP.turn = r.turn ?? (r.box[2] > r.box[3] ? 90 : 0);          // no barcode to go by: landscape → turn
  } else {
    SHIP.crop = [0, 0, SHIP.src.width, SHIP.src.height]; SHIP.how = "none";
    SHIP.turn = SHIP.src.width > SHIP.src.height ? 90 : 0;
  }
  drawShip();
}
function drawSource() {
  const view = $("#src-canvas"), { src, crop } = SHIP;
  $("#src-wrap").hidden = !src;
  if (!src) return;
  const s = Math.min(1, 900 / Math.max(src.width, src.height));
  view.width = Math.round(src.width * s); view.height = Math.round(src.height * s); view.dataset.s = s;
  const ctx = view.getContext("2d");
  ctx.drawImage(src, 0, 0, view.width, view.height);
  const [x, y, w, h] = crop.map(v => v * s);
  ctx.fillStyle = "rgba(20, 30, 50, 0.35)";                     // dim everything outside the label area
  ctx.fillRect(0, 0, view.width, y); ctx.fillRect(0, y + h, view.width, view.height - y - h);
  ctx.fillRect(0, y, x, h); ctx.fillRect(x + w, y, view.width - x - w, h);
  ctx.strokeStyle = "#1f6feb"; ctx.lineWidth = 3; ctx.strokeRect(x, y, w, h);
  $("#crop-note").textContent = { border: "Label found (its border). Drag to redraw the area if needed.",
    content: "Label found (by its barcodes). Check the outline — drag to redraw it if needed.",
    none: "No label found — using the whole image. Drag a box around the label.", manual: "Your area." }[SHIP.how] || "";
}
export function drawShip(canvas = $("#ship-canvas")) {
  const [W, H] = area(CFG.labels.ship);                         // printable 4 × 6: 1199 × 1799
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, W, H);
  const { src, crop, turn } = SHIP;
  $("#ship-print").disabled = $("#ship-clear").disabled = !src;
  if (canvas.id === "ship-canvas") drawSource();
  if (!src) { $("#ship-note").textContent = "UPS / FedEx: paste a screenshot, or drop the label PDF — the whole page is fine."; return canvas; }
  const [bx, by, bw, bh] = crop;
  const side = turn % 180 !== 0;                                // turned a quarter: width and height swap
  const cw = side ? bh : bw, ch = side ? bw : bh;
  const m = 8, s = Math.min((W - 2 * m) / cw, (H - 2 * m) / ch);
  ctx.save();
  ctx.translate(W / 2, H / 2); ctx.rotate(turn * Math.PI / 180);
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(src, bx, by, bw, bh, -bw * s / 2, -bh * s / 2, bw * s, bh * s);
  ctx.restore();
  const dpiIn = Math.round(DPI / s);
  $("#ship-note").textContent = s > 1.8
    ? `Heads-up: only ≈${dpiIn} dpi at label size — barcodes may scan poorly. Zoom in before the screenshot, or use the PDF.`
    : `≈${dpiIn} dpi at label size${turn ? ` · turned ${turn}°` : ""}.`;
  return canvas;
}
// drag on the page view to draw the label area
(() => {
  const view = $("#src-canvas");
  let start = null;
  const at = e => { const r = view.getBoundingClientRect(), k = view.width / r.width / +view.dataset.s;
    return [Math.max(0, Math.min(SHIP.src.width, (e.clientX - r.left) * k)), Math.max(0, Math.min(SHIP.src.height, (e.clientY - r.top) * k))]; };
  view.onpointerdown = e => { if (!SHIP.src) return; start = at(e); view.setPointerCapture(e.pointerId); };
  view.onpointermove = e => {
    if (!start) return;
    const [x, y] = at(e);
    SHIP.crop = [Math.min(x, start[0]), Math.min(y, start[1]), Math.abs(x - start[0]), Math.abs(y - start[1])];
    SHIP.how = "manual"; drawSource();
  };
  view.onpointerup = () => {
    if (!start) return;
    start = null;
    if (SHIP.crop[2] < 20 || SHIP.crop[3] < 20) return findLabel();   // a click, not a drag: back to the detected area
    drawShip();
  };
})();
$("#find-label").onclick = findLabel;
$("#whole-image").onclick = () => { SHIP.crop = [0, 0, SHIP.src.width, SHIP.src.height]; SHIP.how = "manual"; drawShip(); };
$("#rot-left").onclick = () => { SHIP.turn = (SHIP.turn + 270) % 360; drawShip(); };
$("#rot-right").onclick = () => { SHIP.turn = (SHIP.turn + 90) % 360; drawShip(); };
$("#rot-180").onclick = () => { SHIP.turn = (SHIP.turn + 180) % 360; drawShip(); };
$("#ship-open").onclick = () => $("#ship-file").click();
$("#ship-file").onchange = e => { if (e.target.files[0]) loadShip(e.target.files[0]); e.target.value = ""; };
const drop = $("#drop");
drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) loadShip(e.dataTransfer.files[0]); };
document.addEventListener("paste", e => {
  const file = [...e.clipboardData.items].find(i => i.kind === "file")?.getAsFile();
  if (!file) return;
  e.preventDefault(); showTab("ship"); loadShip(file);
});
$("#ship-clear").onclick = () => { Object.assign(SHIP, { src: null, full: null, crop: null, turn: 0, how: "" }); drawShip(); };
$("#ship-print").onclick = async () => {
  const note = `${SHIP.name || "label"} — ${SHIP.how === "manual" ? "hand-cropped" : SHIP.how === "none" ? "whole image" : "label found"}, turned ${SHIP.turn}°`;
  if (await printCanvas("ship", drawShip(document.createElement("canvas")), +$("#ship-copies").value || 1, { note }, SHIP.name || "shipping label"))
    $("#ship-clear").click();
};

// ---- hands-free shipping (Settings, off by default): a label that arrived by itself prints by itself — only when it's
// certain: the label was found on the page, its carrier tracking barcode reads, and that tracking # never printed here
let autoShipCancel = null;
async function autoShip(item) {
  if (!SHIP.src || SHIP.how === "none" || busy) return;
  const canvas = drawShip(document.createElement("canvas"));
  const check = await checkBarcode(canvas);
  if (!check.ok || !check.tracking) {
    return jobbar(`Not printed by itself: ${check.ok ? "no carrier tracking # found" : check.message} — check it and press Print`, "wait");
  }
  const tracking = check.tracking.replace(/\s/g, "");
  let before = [];
  for (const q of new Set([tracking, check.tracking])) {         // stored with or without the spaces FedEx numbers get
    try { before.push(...(await api("history?kind=ship&limit=5&q=" + encodeURIComponent(q))).items.filter(h => h.state !== "failed")); } catch {}
  }
  if (before.length) {
    return jobbar(`${check.carrier} ${check.tracking} was already printed ${before[0].at.slice(0, 10)} — not printed again by itself`,
                  "wait", [["Print anyway", () => $("#ship-print").click()], ["Clear", () => { $("#ship-clear").click(); jobbar(""); }]]);
  }
  let cancelled = false;
  autoShipCancel = () => { cancelled = true; jobbar("Cancelled — press Print when you want it", "wait"); };
  for (let s = 5; s > 0 && !cancelled; s--) {
    jobbar(`Printing ${check.carrier} ${check.tracking} by itself in ${s} s…`, "wait", [["Cancel", autoShipCancel]]);
    await new Promise(r => setTimeout(r, 1000));
  }
  autoShipCancel = null;
  if (cancelled) return;
  const note = `${item.name} — printed by itself (${item.source}), label found, turned ${SHIP.turn}°`;
  if (await printCanvas("ship", canvas, 1, { note }, `${check.carrier} ${check.tracking}`)) $("#ship-clear").click();
}
$("#auto-ship").onchange = async e => {
  try { await api("settings/auto-ship", { on: e.target.checked }); CFG = await api("config");
        toast(e.target.checked ? "Shipping labels from Downloads print by themselves" : "Shipping labels wait for you again"); }
  catch (err) { toast(err.message, true); e.target.checked = !!CFG.autoShip; }
};

// ------------------------------------------------------------------ history
let HIST = [];
// History: searched on the server over everything ever printed on this PC; 60 at a time, "Show more" for older
const HIST_PAGE = 60;
function histQuery() {
  const p = new URLSearchParams();
  const v = { q: $("#hist-filter").value.trim(), kind: $("#hist-kind").value, since: $("#hist-since").value, until: $("#hist-until").value };
  for (const [k, x] of Object.entries(v)) if (x) p.set(k, x);
  return p;
}
async function loadHistory(more = false) {
  const p = histQuery();
  $("#hist-csv").href = "api/history.csv" + (p.toString() ? "?" + p : "");
  p.set("limit", HIST_PAGE);
  if (more && HIST.length) p.set("before", HIST[HIST.length - 1].id);
  const items = (await api("history?" + p)).items;
  HIST = more ? HIST.concat(items) : items;
  $("#hist-more").hidden = items.length < HIST_PAGE;
  $("#hist-count").textContent = histQuery().toString() ? `${HIST.length}${items.length < HIST_PAGE ? "" : "+"} found` : `newest first`;
  renderHistory();
}
let histTimer;
const histSearch = () => { clearTimeout(histTimer); histTimer = setTimeout(() => loadHistory(), 250); };
["#hist-filter"].forEach(s => $(s).oninput = histSearch);
["#hist-kind", "#hist-since", "#hist-until"].forEach(s => $(s).onchange = () => loadHistory());
$("#hist-more").onclick = () => loadHistory(true);
function renderHistory() {
  const rows = HIST;
  const state = h => ({ done: "✓", failed: `<span class="bad" title="${esc(h.message)}">✗ not printed</span>`,
                         sent: "…", sending: "…" }[h.state] ?? "");
  $("#history tbody").innerHTML = rows.map(h => `<tr><td>${esc(h.at.replace("T", " ").slice(0, 16))}</td>
    <td>${h.kind === "tag" ? "Inventory tag" : "Shipping"}</td>
    <td>${h.kind === "tag" ? (h.fields.free != null ? `<i>Blank tag</i> · ${esc(h.fields.free.replace(/\n/g, " / "))}`
        : `<b>${esc(h.fields.customer)}</b> · ${esc(usDate(h.fields.received))} · #${esc(h.fields.ticket)}`)
        : `${h.image ? `<img class="thumb" src="api/history/${h.id}/image" alt="" loading="lazy">` : ""}${h.tracking ? `<b>${esc(h.tracking)}</b> ` : ""}<span class="hint">${esc(h.fields.note || "")}</span>`}</td>
    <td>${h.copies}</td><td>${state(h)}</td><td><button class="ghost" data-id="${h.id}">Reprint</button></td></tr>`).join("")
    || `<tr><td colspan="6" class="hint">Nothing printed yet.</td></tr>`;
  $$("#history button[data-id]").forEach(b => b.onclick = async () => {
    const h = HIST.find(x => x.id == b.dataset.id);
    if (h.kind === "tag") {
      await printCanvas("tag", await tagCanvas(h.fields), 1, h.fields, tagWhat(h.fields) + " (reprint)", { force: true });
    } else {
      try {
        const img = await decodeImage(await (await fetch(`api/history/${h.id}/image`)).blob());
        const c = document.createElement("canvas"); c.width = img.width; c.height = img.height;
        c.getContext("2d").drawImage(img, 0, 0);
        await printCanvas("ship", c, 1, { ...h.fields, reprint: h.id }, (h.tracking || "shipping label") + " (reprint)", { force: true });
      } catch (err) { jobbar("✗ " + err.message, "bad"); }
    }
    setTimeout(loadHistory, 1500);
  });
}


// ------------------------------------------------------------------ tabs, printers, keys
function showTab(t) {
  $$("nav button").forEach(b => b.classList.toggle("on", b.dataset.tab === t));
  $$(".tab").forEach(s => s.hidden = s.id !== "tab-" + t);
  if (t === "history") loadHistory();
  if (t === "tag") form.ticket.focus();
  if (t === "settings") loadCW();
  if (t === "ship") drop.focus();
}
$$("nav button").forEach(b => b.onclick = () => showTab(b.dataset.tab));
document.addEventListener("keydown", e => {
  if (e.key === "Enter" && !$("#tab-ship").hidden && SHIP.src && !e.target.closest("input, textarea")) $("#ship-print").click();
});
// the roll the printer reports (550 series): which labels and how many are left; "" when unknown
function rollText(r) {
  if (!r) return "";
  if (!r.canPrint) return ` · ${r.media}`;
  return ` · ${r.stock || r.sku || "labels"}${r.remaining != null ? ` · ${r.remaining} left` : ""}${r.low ? " (low)" : ""}`;
}
let rollSwitched = "", eventsAfter = 0;
async function loadPrinters() {
  try {
    const p = await api("printers");
    $("#printers").innerHTML = [["tag", "550 Turbo"], ["ship", "5XL"]].map(([k, n]) => {
      const r = p[k].roll, low = r && (r.low || !r.canPrint);
      return `<span class="${p[k].ok ? "ok" : ""}${low ? " low" : ""}" title="${esc(p[k].status)}${r?.name ? " — " + esc(r.name) : ""}">${n}` +
        `${p[k].ok ? esc(rollText(r)) : `: ${esc(p[k].status)}`}` +
        `${p[k].paused ? ` <button class="linkish" data-resume="${k}">Resume</button>` : ""}</span>`;
    }).join("");
    // the 550 Turbo knows its roll: tags follow it (once per change — the user can still pick in Settings)
    const tr = p.tag.roll;
    if (tr?.stock && CFG.tagStocks[tr.stock] && tr.stock !== CFG.tagLabel && rollSwitched !== tr.stock) {
      rollSwitched = tr.stock;
      try {
        await api("settings/tag-label", { label: tr.stock });
        CFG = await api("config"); drawTagPreview(); $("#tag-label").value = CFG.tagLabel;
        $("#tag-stock").textContent = `${CFG.tagLabel} · ${CFG.labels.tag.size}`;
        toast(`The 550 Turbo has ${tr.name} labels loaded — tags now print on those`);
      } catch (err) { toast(err.message, true); }
    }
    $("#roll-auto").textContent = tr?.stock ? `The 550 Turbo reports ${tr.name}${tr.remaining != null ? `, ${tr.remaining} left` : ""}: LabelDesk picks this by itself.` : "";
    showNetwork(p.network);
    showPrinterCards(p);
    const ev = (await api("printers/events?after=" + eventsAfter)).events;
    for (const e of ev) { toast(e.text, e.level === "bad"); eventsAfter = Math.max(eventsAfter, e.id); }
    $$("[data-resume]").forEach(b => b.onclick = async () => {
      try { await api(`printers/${b.dataset.resume}/resume`, {}); } catch (err) { toast(err.message, true); }
      loadPrinters();
    });
  } catch { $("#printers").innerHTML = `<span>LabelDesk server not answering</span>`; }
}
// Settings → Printers: one card per printer — state, roll, labels left, where it is
function showPrinterCards(p) {
  $("#printer-cards").innerHTML = [["tag", "550 Turbo · tags"], ["ship", "5XL · shipping"]].map(([k, n]) => {
    const x = p[k], r = x.roll;
    return `<div><b>${n}</b>
      <span class="${x.ok ? "" : "bad"}">${esc(x.status)}</span><br>
      ${r ? `Roll: ${esc(r.name || r.sku || "unknown")}${r.remaining != null ? ` · <b style="display:inline">${r.remaining}</b> left` : ""}${r.low ? " · <span class='bad'>low</span>" : ""}<br>`
          : `<span class="hint">Roll: not reported</span><br>`}
      <span class="hint">Queue ${esc(x.queue || "—")}</span></div>`;
  }).join("");
}
// Settings → Printers on the network
const MODEL = { "550T": "LabelWriter 550 Turbo", "550": "LabelWriter 550", "5XL": "LabelWriter 5XL" };
function showNetwork(n) {
  if (!n) return;
  const offers = new Map(n.offers.map(o => [o.ip, o]));
  const rows = n.found.map(f => {
    const o = offers.get(f.ip), what = f.model === "5XL" ? "shipping labels" : "tags";
    const btn = o ? ` <button class="linkish" data-use="${o.kind}" data-ip="${esc(f.ip)}">Use for ${what}</button>` : "";
    return `<li class="${o ? "" : "ok"}">${esc(MODEL[f.model] || f.model)} · ${esc(f.ip)} <span class="hint">${esc(f.name)}${o ? "" : " — in use"}</span>${btn}</li>`;
  });
  const blocked = n.error ? (CFG.platform === "mac"
      ? "macOS doesn't let LabelDesk look for printers on the network by itself yet (Local Network privacy). Printing works; set printers up with tools/add-printers.sh."
      : `Looking for printers didn't work (${n.error}). Printing works; set printers up as before.`) : "";
  $("#net-printers").innerHTML = rows.join("") || `<li>${n.scanning ? "Looking…" : !n.auto ? "Looking for printers is off (config.json auto_printers)."
    : blocked || "No DYMO printers announced themselves on this network (they may still print — see the bar at the top)."}</li>`;
  $$("[data-use]").forEach(b => b.onclick = async () => {
    try { await api("printers/use", { kind: b.dataset.use, ip: b.dataset.ip }); } catch (err) { toast(err.message, true); }
    loadPrinters();
  });
}
$("#net-scan").onclick = async () => {
  $("#net-printers").innerHTML = "<li>Looking…</li>";
  try { await api("printers/scan", {}); } catch (err) { toast(err.message, true); }
  loadPrinters();
};

// a data: URL → Blob without fetch() (the page's CSP only lets fetch reach LabelDesk itself)
function dataBlob(url) {
  const [head, b64] = url.split(",", 2), bin = atob(b64), bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: head.slice(5).split(";")[0] });
}

// ---- new labels arriving by themselves: a carrier PDF saved to Downloads, or "print" to the LabelDesk printer
let inboxAfter = 0;
async function pollInbox(open = true) {
  let items;
  try { items = (await api("inbox?after=" + inboxAfter)).items; } catch { return; }
  if (!items.length) return;
  inboxAfter = Math.max(...items.map(i => i.id));
  if (!open) return;
  const item = items[items.length - 1];
  let src, blob;
  try {
    const d = await api("inbox/" + item.id);
    blob = dataBlob(d.pdf || d.png);
    if (d.verify) {                                           // a new PDF in Downloads: only a shipping label counts
      const page = await pdfPage(await blob.arrayBuffer());
      if (!LABEL_WORDS.test(page.text)) return;
      src = page.canvas;
    }
  } catch (e) { console.warn("inbox:", item.name, e); return; }   // not a readable PDF / gone already: not ours
  const openIt = async () => {
    showTab("ship");
    if (src) useShipSource(src, item.name); else await loadShip(blob, item.name);
    toast(`New label from ${item.source}: ${item.name}`);
    if (CFG.autoShip) await autoShip(item);
  };
  if (SHIP.src) jobbar(`New label from ${item.source}: ${item.name}`, "wait", [["Open it", openIt], ["Later", () => jobbar("")]]);
  else openIt();
}

document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "r" && !$("#tab-tag").hidden) { e.preventDefault(); printLastTag(); }
});

// the "Date received" follows the calendar (an app window left open overnight) unless someone set it by hand
let autoDate = today();
form.received.addEventListener("change", () => { autoDate = form.received.value === today() ? today() : null; });
function rollDate() {
  if (autoDate && autoDate !== today() && form.received.value === autoDate) { form.received.value = autoDate = today(); drawTagPreview(); }
}
document.addEventListener("visibilitychange", rollDate);
window.addEventListener("focus", rollDate);

(async () => {
  CFG = await api("config");
  form.received.value = today();
  setInterval(rollDate, 60000);
  $("#flip").checked = flip();
  $("#tag-label").value = CFG.tagLabel;
  $("#tag-barcode").value = CFG.tagBarcode || "code128";
  $("#auto-ship").checked = !!CFG.autoShip;
  $("#tag-stock").textContent = `${CFG.tagLabel} · ${CFG.labels.tag.size}`;
  try { form.showContact.checked = JSON.parse(localStorage.getItem("showContact")) ?? false; } catch {}
  $("#win-printer").hidden = $("#win-dymo").hidden = CFG.platform !== "windows";
  $("#about-version").textContent = "version " + CFG.version;
  loadCW();                                                     // may wait on ConnectWise — never hold up the app
  loadVersions();                                               // Settings → Version (asks GitHub; never holds up the app)
  await (tagLogoReady = loadLogo());                            // the logo is part of the tag: draw (and print) with it
  await templateImagesReady(activeTemplate());
  showOffset(); showTemplates(); drawTagPreview(); showLogoState(); drawShip(); loadPrinters(); loadCustomers();
  setInterval(loadPrinters, 15000);
  await pollInbox(false); setInterval(pollInbox, 2000);          // only labels that arrive from now on
})();

// ---- intake: a barcode scanner types the serial and presses Enter — move on instead of printing
form.serial.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); form.bin.focus(); } });
form.bin.addEventListener("keydown", e => { if (e.key === "Enter" && !form.ticket.value.trim()) { e.preventDefault(); form.ticket.focus(); } });
$$("#acc-chips .chip").forEach(b => b.onclick = () => {
  const list = accessories();
  if (!list.some(x => x.toLowerCase() === b.textContent.toLowerCase())) list.push(b.textContent);
  form.accessories.value = list.join(", "); drawTagPreview();
});
["serial", "bin", "accessories"].forEach(n => form[n].addEventListener("input", () => drawTagPreview()));
