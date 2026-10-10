// Browser check (driven by tests/browser_check.sh): the real page in a real Chrome, over the DevTools protocol.
//   node check.mjs <devtools port> <sample pdf> <downloads dir>
// 1. pdf.js opens the sample and reads its text          (pdfPage — a PDF that won't open breaks the Shipping tab)
// 2. the same PDF saved to Downloads opens by itself on the Shipping tab, label found  (inbox → dataBlob → loadShip)
// 3. hands-free shipping counts down and can be cancelled
// 4. Batch → Open spreadsheet (a real .xlsx) maps the columns
// 5. no uncaught errors or inbox warnings on the page
import { copyFileSync, readFileSync } from "node:fs";
import { basename, join } from "node:path";

const [port, pdf, downloads] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));

let page;
for (let i = 0; i < 40 && !page; i++) {
  try { page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find(t => t.type === "page" && t.url.startsWith("http://127.0.0.1")); }
  catch { /* Chrome still starting */ }
  if (!page) await sleep(250);
}
if (!page) { console.error("✗ Chrome never showed the LabelDesk page"); process.exit(1); }

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((ok, bad) => { ws.onopen = ok; ws.onerror = bad; });
let id = 0; const pending = {}, problems = [];
ws.onmessage = e => {
  const m = JSON.parse(e.data);
  if (m.id && pending[m.id]) return pending[m.id](m);
  if (m.method === "Runtime.exceptionThrown") problems.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
  if (m.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(m.params.type))
    problems.push(m.params.args.map(a => a.value ?? a.description).join(" "));
};
const send = (method, params = {}) => new Promise(r => { pending[++id] = r; ws.send(JSON.stringify({ id, method, params })); });
const run = async expr => {
  const r = (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result;
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
};
await send("Runtime.enable");

let failed = 0;
const check = (ok, what, detail = "") => { console.log(`${ok ? "✓" : "✗"} ${what}${detail ? " — " + detail : ""}`); if (!ok) failed++; };

// wait for the app to finish starting (it polls the inbox from then on)
for (let i = 0; i < 40 && !(await run("!!document.querySelector('.printers') && document.readyState === 'complete'").catch(() => false)); i++) await sleep(250);
await sleep(1500);

const b64 = readFileSync(pdf).toString("base64");
const text = await run(`(async () => { const m = await import("/app.js");
  const bin = atob("${b64}"), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  const p = await m.pdfPage(u.buffer); return p.canvas.width + "x" + p.canvas.height + " " + p.text; })()`).catch(e => "ERR " + e.message);
check(/^\d+x\d+ .*UPS/s.test(text), "pdf.js opens the sample PDF and reads its text", text.slice(0, 60));

copyFileSync(pdf, join(downloads, "browser-check-" + basename(pdf)));
let state = null;
for (let i = 0; i < 40; i++) {
  await sleep(500);
  state = await run(`(async () => { const m = await import("/app.js");
    return { tab: !document.getElementById("tab-ship").hidden, src: !!m.SHIP.src, how: m.SHIP.how }; })()`).catch(() => null);
  if (state?.src) break;
}
check(state?.tab && state?.src, "a label saved to Downloads opens by itself on the Shipping tab", JSON.stringify(state));
check(!!state?.how && state.how !== "none", "the label is found on the page", state?.how || "");
// 4. hands-free shipping (Settings, opt-in): the next label from Downloads counts down by itself — cancelled here
await run(`(() => { document.getElementById("ship-clear").click(); const c = document.getElementById("auto-ship");
  if (!c.checked) c.click(); return true; })()`);
await sleep(800);
copyFileSync(pdf, join(downloads, "browser-check-2-" + basename(pdf)));
let bar = "";
for (let i = 0; i < 40; i++) {
  await sleep(500);
  bar = await run(`document.querySelector("#jobbar .msg")?.textContent || ""`).catch(() => "");
  if (/by itself/.test(bar)) break;
}
check(/printing .* by itself in \d s/i.test(bar), "a label from Downloads counts down to print by itself (opt-in)", bar.slice(0, 90));
await run(`(() => { const b = [...document.querySelectorAll("#jobbar button")].find(b => b.textContent === "Cancel"); b?.click(); return !!b; })()`);
await sleep(1500);
bar = await run(`document.querySelector("#jobbar .msg")?.textContent || ""`).catch(() => "");
check(/Cancelled/.test(bar), "Cancel stops it", bar.slice(0, 60));
await run(`(() => { const c = document.getElementById("auto-ship"); if (c.checked) c.click(); return true; })()`);
// 5. Batch → Open spreadsheet: the real .xlsx sample through the file picker → columns guessed → 3 devices, 6 tags
await run(`(() => { document.querySelector('[data-tab="tag"], nav button')?.click(); document.getElementById("tag-batch").hidden = false; return true; })()`);
const doc = await send("DOM.getDocument", { depth: -1 });
const inp = await send("DOM.querySelector", { nodeId: doc.result.root.nodeId, selector: "#sheet-file" });
await send("DOM.setFileInputFiles", { nodeId: inp.result.nodeId, files: [new URL("../samples/intake.xlsx", import.meta.url).pathname] });
await run(`(() => { document.getElementById("sheet-file").dispatchEvent(new Event("change")); return true; })()`);
let sheetState = null;
for (let i = 0; i < 20; i++) {
  await sleep(300);
  sheetState = await run(`(() => ({ shown: !document.getElementById("sheet").hidden, button: document.getElementById("sheet-print").textContent,
    rows: document.querySelectorAll("#sheet-preview tr").length - 1,
    map: [...document.querySelectorAll("#sheet-map select")].map(s => s.dataset.field + "=" + (s.selectedOptions[0]?.textContent || "")).join(", "),
    first: document.querySelector("#sheet-preview tr:nth-child(2)")?.textContent || "" }))()`).catch(() => null);
  if (sheetState?.shown) break;
}
check(sheetState?.shown && sheetState.rows === 3 && /Print 6 tags \(3 devices\)/.test(sheetState.button),
      "an Excel sheet opens in Batch with its columns mapped", `${sheetState?.button} · ${sheetState?.map}`);
check(/75013.*Acme Dental Group.*Jane Smith.*10\/09\/2026.*PF3XK2LQ.*B3.*Charger, Bag/.test(sheetState?.first || ""),
      "the first row is read right (date, serial, accessories)", (sheetState?.first || "").slice(0, 90));
// 6. intake: a scanned serial says whether LabelDesk has seen it; History → Scan a tag shows the ticket
const intake = await run(`(async () => { document.getElementById("sheet-close")?.click();
  const s = document.querySelector("#tag-form [name=serial]"); s.value = "PF3XK2LQ";
  s.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); await new Promise(r => setTimeout(r, 800));
  const moved = document.activeElement?.name;
  const info = document.getElementById("dev-info").textContent;
  document.querySelector('nav [data-tab="history"]')?.click(); await new Promise(r => setTimeout(r, 300));
  const scan = document.getElementById("scan"); scan.value = "75013";
  scan.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); await new Promise(r => setTimeout(r, 800));
  return { moved, info, scan: document.getElementById("scan-out").textContent }; })()`).catch(e => ({ err: e.message }));
check(intake.moved === "bin" && /First time/.test(intake.info || ""), "a scanned serial moves on (no print) and is looked up", JSON.stringify(intake).slice(0, 120));
check(/Ticket #75013/.test(intake.scan || ""), "History → Scan a tag shows the ticket", (intake.scan || "").slice(0, 80));
// 7. the designer: another label size, things added, saved; only tag-sized layouts can be the tag's layout
const dz = await run(`(async () => {
  document.querySelector('nav [data-tab="designer"]').click(); await new Promise(r => setTimeout(r, 600));
  const tagOk0 = !document.getElementById("dz-tag").disabled, c = document.getElementById("dz-canvas"), size0 = c.width + "x" + c.height;
  const st = document.getElementById("dz-stock"); st.value = "w72h154.1"; st.dispatchEvent(new Event("change"));
  for (const k of ["text", "qr", "box"]) document.querySelector('#dz-add [data-add="' + k + '"]').click();
  await new Promise(r => setTimeout(r, 600));
  document.getElementById("dz-name").value = "Small label"; document.getElementById("dz-name").dispatchEvent(new Event("input"));
  document.getElementById("dz-save").click();
  return { tagOk0, size0, size1: c.width + "x" + c.height, objects: document.querySelectorAll("#dz-objects li[data-i]").length,
           tagOk1: !document.getElementById("dz-tag").disabled, saved: JSON.parse(localStorage.getItem("tagTemplates") || "[]").map(t => t.name + "@" + t.stock) };
})()`).catch(e => ({ err: e.message }));
check(dz.size0 === "962x298" && dz.size1 === "592x270", "the designer draws the chosen label at 300 dpi", JSON.stringify(dz).slice(0, 160));
check(dz.objects === 6 && dz.saved?.includes("Small label@w72h154.1"), "things are added and the layout is saved");
check(dz.tagOk0 === true && dz.tagOk1 === false, "only tag-sized layouts can be the inventory tag's layout");
check(!problems.length, "no errors on the page", problems.join(" | ").slice(0, 300));

ws.close();
process.exit(failed ? 1 : 0);
