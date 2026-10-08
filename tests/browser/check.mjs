// Browser check (driven by tests/browser_check.sh): the real page in a real Chrome, over the DevTools protocol.
//   node check.mjs <devtools port> <sample pdf> <downloads dir>
// 1. pdf.js opens the sample and reads its text          (pdfPage — a PDF that won't open breaks the Shipping tab)
// 2. the same PDF saved to Downloads opens by itself on the Shipping tab, label found  (inbox → dataBlob → loadShip)
// 3. no uncaught errors or inbox warnings on the page
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
check(!problems.length, "no errors on the page", problems.join(" | ").slice(0, 300));

ws.close();
process.exit(failed ? 1 : 0);
