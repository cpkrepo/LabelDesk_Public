// Imported DYMO Connect templates (.dymo) for the inventory tag. LabelDesk renders them itself at 300 dpi — the preview
// is still the print. Format (checked on DYMO's DCD-SDK-Sample files): XML DesktopLabel > DYMOLabel with Orientation,
// LabelName, DYMORect (printable area on the label, inches) and LabelObjects (TextObject / AddressObject / BarcodeObject…),
// each with ObjectLayout DYMOPoint X/Y + Size Width/Height in INCHES (label coordinates) and fonts in points.
//
// Each object gets a `format`: its text with {company} {customer} {received} {ticket} where the form's values go.
// Import guesses them from the object names / sample text; the user checks them in the template panel.
// Templates live per PC (localStorage), like Rotate 180° and the text position.

const FIELDS = ["company", "customer", "received", "ticket", "serial", "bin", "item"];
const DPI = 300;
const FONT_STACK = '"DejaVu Sans", "Liberation Sans", Arial, sans-serif';

const num = (el, sel) => parseFloat(el.querySelector(sel)?.textContent ?? "") || 0;
const txt = (el, sel) => el.querySelector(sel)?.textContent?.trim() ?? "";

// DYMO Connect's BarcodeFormat / QR objects → web/barcodes.js (anything unknown draws as Code 128, like before)
export function symbologyOf(dymoFormat) {
  const f = String(dymoFormat || "").toLowerCase();
  if (f.startsWith("qr")) return "qr";
  if (f.startsWith("code39")) return "code39";
  if (f === "upca" || f === "upc") return "upca";
  if (f.startsWith("ean13")) return "ean13";
  return "code128";
}

// ---- import ---------------------------------------------------------------------------------------------------------
export function parseDymo(xml, fileName = "template") {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  if (doc.querySelector("parsererror")) throw new Error("not an XML file");
  const label = doc.querySelector("DYMOLabel");
  if (!label) throw new Error("not a DYMO Connect label (.dymo) file");
  const rectEl = label.querySelector(":scope > DYMORect");
  const rect = rectEl ? { x: num(rectEl, "DYMOPoint > X"), y: num(rectEl, "DYMOPoint > Y"),
                          w: num(rectEl, "Size > Width"), h: num(rectEl, "Size > Height") } : null;
  const objects = [];
  for (const o of label.querySelectorAll("LabelObjects > *")) {
    const lay = o.querySelector(":scope > ObjectLayout");
    if (!lay) continue;
    const box = { x: num(lay, "DYMOPoint > X"), y: num(lay, "DYMOPoint > Y"), w: num(lay, "Size > Width"), h: num(lay, "Size > Height") };
    const name = txt(o, ":scope > Name");
    const halign = txt(o, ":scope > HorizontalAlignment") || "Left", valign = txt(o, ":scope > VerticalAlignment") || "Middle";
    if (o.tagName === "ImageObject") {                                    // e.g. the shop logo: an embedded picture
      const src = embeddedImage(o);
      if (src) objects.push({ kind: "image", name, ...box, halign: txt(o, ":scope > HorizontalAlignment") || "Center", src, sample: "(picture)", format: "",
                              scale: txt(o, ":scope > ScaleMode") || "Uniform" });
      continue;
    }
    if (o.tagName === "QRCodeObject") {                                    // DYMO Connect's QR object (its data: Data/DataString)
      const data = [...o.querySelectorAll("DataString, Data > *")].map(d => d.textContent).join("") || txt(o, ":scope > Data");
      objects.push({ kind: "barcode", name, ...box, halign, format: guessFormat(name, data, true), sample: data, symbology: "QRCode" });
      continue;
    }
    if (o.tagName === "BarcodeObject") {
      const data = [...o.querySelectorAll("DataString")].map(d => d.textContent).join("");
      objects.push({ kind: "barcode", name, ...box, halign, format: guessFormat(name, data, true), sample: data,
                     symbology: txt(o, ":scope > BarcodeFormat") });
      continue;
    }
    const lines = [...o.querySelectorAll("LineTextSpan")].map(line => {
      const spans = [...line.querySelectorAll("TextSpan")];
      const fi = spans[0]?.querySelector("FontInfo");
      return { text: spans.map(s => txt(s, ":scope > Text")).join(""),
               size: fi ? num(fi, "FontSize") || 10 : 10, bold: fi ? txt(fi, "IsBold") === "True" : false,
               italic: fi ? txt(fi, "IsItalic") === "True" : false };
    });
    if (!lines.length) continue;                                          // shapes, images: not drawn (yet)
    const text = lines.map(l => l.text).join("\n");
    objects.push({ kind: "text", name, ...box, halign, valign, fit: txt(o, ":scope > FitMode") || "None",
                   lines, sample: text, format: guessFormat(name, text, false) });
  }
  if (!objects.length) throw new Error("no text or barcode objects in this template");
  const orientation = txt(label, ":scope > Orientation") || "Landscape";
  return { id: `t${Date.now()}`, name: fileName.replace(/\.dymo$/i, ""), labelName: txt(label, ":scope > LabelName"),
           orientation, rect, objects };
}

// The picture inside an ImageObject: the first child element holding base64 image data (DYMO Label .label files call it
// <Image>; found by content, not by element name, so a DYMO Connect .dymo file with a different tag name works too).
const MAGIC = [["iVBORw0KGgo", "image/png"], ["/9j/", "image/jpeg"], ["R0lGOD", "image/gif"], ["Qk", "image/bmp"]];
function embeddedImage(o) {
  for (const el of o.querySelectorAll("*")) {
    if (el.children.length) continue;
    const b64 = (el.textContent || "").replace(/\s+/g, "");
    if (b64.length < 64 || !/^[A-Za-z0-9+/=]+$/.test(b64)) continue;
    const m = MAGIC.find(([p]) => b64.startsWith(p));
    if (m) return `data:${m[1]};base64,${b64}`;
  }
  return null;
}
// decoded pictures, black and white like the printer prints them (shared by every template using the same picture)
const IMAGES = new Map();
function picture(src) {
  let e = IMAGES.get(src);
  if (!e) {
    e = { img: new Image(), bw: null };
    e.ready = new Promise(res => { e.img.onload = e.img.onerror = res; });
    e.img.src = src; IMAGES.set(src, e);
  }
  return e;
}
export function templateImagesReady(tpl) {
  return Promise.all((tpl?.objects || []).filter(o => o.kind === "image").map(o => picture(o.src).ready));
}
function bwOf(img) {
  const c = document.createElement("canvas"); c.width = img.naturalWidth; c.height = img.naturalHeight;
  const ctx = c.getContext("2d"); ctx.drawImage(img, 0, 0);
  const d = ctx.getImageData(0, 0, c.width, c.height), p = d.data;
  for (let i = 0; i < p.length; i += 4) {
    const lum = (0.299 * p[i] + 0.587 * p[i + 1] + 0.114 * p[i + 2]) * p[i + 3] / 255 + 255 - p[i + 3];
    p[i] = p[i + 1] = p[i + 2] = lum < 128 ? 0 : 255; p[i + 3] = 255;
  }
  ctx.putImageData(d, 0, 0); return c;
}

// {field} guesses: object names first (DYMO users often name objects), then what the sample text looks like.
export function guessFormat(name, text, barcode) {
  const n = (name || "").toLowerCase();
  if (barcode) return "{ticket}";
  const has = re => re.test(text);
  if (/ticket|tkt/.test(n) || has(/ticket/i))                               // "Ticket#: 75013" → "Ticket#: {ticket}"
    return has(/\d{3,}/) ? text.replace(/\d{3,}(?!.*\d{3,})/s, "{ticket}") : has(/ticket/i) ? `${text.trimEnd()} {ticket}` : "{ticket}";
  const DATE = /\d{1,2}\/\d{1,2}\/\d{2,4}/;
  if (/receiv|date/.test(n) || has(DATE) || has(/receiv/i))                 // "Received: 09/30/2026" → "Received: {received}"
    return has(DATE) ? text.replace(DATE, "{received}") : has(/receiv/i) ? `${text.trimEnd()} {received}` : "{received}";
  if (/serial|s\/n|\bsn\b/.test(n) || has(/^\s*(s\/n|serial)/i))            // "S/N: PF3XK2LQ" → "S/N: {serial}"
    return has(/^\s*(s\/n|serial)[^:]*:/i) ? text.replace(/(:\s*).*$/s, "$1{serial}") : "{serial}";
  if (/\bbin\b|shelf|location/.test(n)) return has(/:/) ? text.replace(/(:\s*).*$/s, "$1{bin}") : "{bin}";
  if (/accessor|item|part/.test(n)) return "{item}";
  if (/contact|customer|person/.test(n)) return "{customer}";
  if (/company|client|name|address/.test(n)) return "{company}";
  return text;                                                             // static text (shop name, notes…)
}

// ---- render (design space: the tag's length across, DW × DH px; the caller has already turned/flipped/offset ctx) ----
export function drawTemplate(ctx, tpl, f, DW, DH, { drawBarcode, usDate }) {
  const r = tpl.rect || { x: 0, y: 0, w: DW / DPI, h: DH / DPI };
  const s = Math.min(DW / (r.w * DPI), DH / (r.h * DPI));                 // DYMO's printable rect → ours (≈ 1)
  const px = v => v * DPI * s;
  const values = { company: f.customer || "", customer: f.contact || "", received: usDate(f.received), ticket: f.ticket || "",
                   serial: f.serial || "", bin: f.bin || "", item: f.item ? `${f.item}${f.part ? ` (${f.part})` : ""}` : (f.part || "") };
  const fill = fmt => fmt.replace(/\{(\w+)\}/g, (m, k) => (k in values ? values[k] : m));
  ctx.fillStyle = "#000"; ctx.textBaseline = "alphabetic";
  for (const o of tpl.objects) {
    const x = px(o.x - r.x), y = px(o.y - r.y), w = px(o.w), h = px(o.h);
    if (o.kind === "image") {
      const e = picture(o.src);
      if (!e.img.complete || !e.img.naturalWidth) continue;               // still loading: templateImagesReady() first
      e.bw = e.bw || bwOf(e.img);
      const iw = e.img.naturalWidth, ih = e.img.naturalHeight;
      let dw = w, dh = h;
      if (o.scale !== "Fill" && o.scale !== "Stretch") { const k = Math.min(w / iw, h / ih); dw = iw * k; dh = ih * k; }
      const dx = o.halign === "Left" ? x : o.halign === "Right" ? x + w - dw : x + (w - dw) / 2;
      ctx.drawImage(e.bw, dx, y + (h - dh) / 2, dw, dh);
      continue;
    }
    if (o.kind === "shape") {                                              // designer: line / box / filled box
      const t = Math.max(1, Math.round((o.stroke || 0.02) * DPI * s));
      if (o.shape === "fill") ctx.fillRect(x, y, w, h);
      else if (o.shape === "box") { ctx.lineWidth = t; ctx.strokeRect(x + t / 2, y + t / 2, w - t, h - t); }
      else if (w >= h) ctx.fillRect(x, y + (h - t) / 2, w, t);                // a line: across the longer side of its box
      else ctx.fillRect(x + (w - t) / 2, y, t, h);
      continue;
    }
    if (o.kind === "barcode") {
      const data = fill(o.format).trim();
      if (data) drawBarcode(ctx, data, x, y, w, h, symbologyOf(o.symbology));
      continue;
    }
    const texts = fill(o.format).split("\n");
    const styles = texts.map((_, i) => o.lines[Math.min(i, o.lines.length - 1)]);
    // point size → px at 300 dpi; AlwaysFit/ShrinkToFit shrink until every line fits the box (DYMO grows too — capped)
    let k = 1;
    const font = (st, kk) => `${st.italic ? "italic " : ""}${st.bold ? "700" : "400"} ${Math.max(6, st.size / 72 * DPI * s * kk)}px ${FONT_STACK}`;
    const measure = kk => {
      let H = 0, W = 0;
      texts.forEach((t, i) => { ctx.font = font(styles[i], kk); W = Math.max(W, ctx.measureText(t).width); H += styles[i].size / 72 * DPI * s * kk * 1.15; });
      return [W, H];
    };
    if (o.fit !== "None") {
      let [mw, mh] = measure(1);
      if (o.fit === "AlwaysFit" && mw < w && mh < h) k = Math.min(w / mw, h / mh, 3);          // grow, like DYMO
      for (let i = 0; i < 60; i++) { [mw, mh] = measure(k); if (mw <= w && mh <= h) break; k *= 0.95; }
    }
    const [, th] = measure(k);
    let ty = o.valign === "Top" ? y : o.valign === "Bottom" ? y + h - th : y + (h - th) / 2;
    texts.forEach((t, i) => {
      const lh = styles[i].size / 72 * DPI * s * k;
      ctx.font = font(styles[i], k);
      const tw = ctx.measureText(t).width;
      const tx = o.halign === "Center" ? x + (w - tw) / 2 : o.halign === "Right" ? x + w - tw : x;
      ty += lh * 1.15;
      ctx.fillText(t, tx, ty - lh * 0.22);
    });
  }
}

// ---- storage (per PC) ------------------------------------------------------------------------------------------------
export const loadTemplates = () => { try { return JSON.parse(localStorage.getItem("tagTemplates")) || []; } catch { return []; } };
export const saveTemplates = list => { try { localStorage.setItem("tagTemplates", JSON.stringify(list)); } catch {} };
export const activeTemplateId = () => { try { return localStorage.getItem("tagTemplate") || ""; } catch { return ""; } };
export const setActiveTemplate = id => { try { id ? localStorage.setItem("tagTemplate", id) : localStorage.removeItem("tagTemplate"); } catch {} };
export const activeTemplate = () => loadTemplates().find(t => t.id === activeTemplateId()) || null;
export { FIELDS };
