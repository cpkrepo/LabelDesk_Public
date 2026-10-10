// Render harness: draws sample labels with the real app code and dumps them as PNG data URLs into the page.
import { drawTag, drawLabel, C128 } from "./app.js";
import { parseDymo, templateImagesReady } from "./template.js";
// a small DYMO Connect-style template (30321-ish): company line, ticket line, ticket barcode — inches, like .dymo files
// an 8×8 black PNG standing in for a template's embedded picture (DYMO files carry the picture as base64)
const PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAAAAADhZOFXAAAADElEQVR4nGNgoA4AAABIAAEuuDx+AAAAAElFTkSuQmCC";
const obj = (tag, name, x, y, w, h, inner) => `<${tag}><Name>${name}</Name>${inner}<ObjectLayout><DYMOPoint><X>${x}</X><Y>${y}</Y></DYMOPoint>` +
  `<Size><Width>${w}</Width><Height>${h}</Height></Size></ObjectLayout></${tag}>`;
const span = (t, pt, bold) => `<FormattedText><LineTextSpan><TextSpan><Text>${t}</Text><FontInfo><FontSize>${pt}</FontSize>` +
  `<IsBold>${bold ? "True" : "False"}</IsBold></FontInfo></TextSpan></LineTextSpan></FormattedText><FitMode>AlwaysFit</FitMode>`;
const DYMO = `<?xml version="1.0"?><DesktopLabel><DYMOLabel><Orientation>Landscape</Orientation><LabelName>Address30321</LabelName>
  <DYMORect><DYMOPoint><X>0.06</X><Y>0.05</Y></DYMOPoint><Size><Width>3.2</Width><Height>1.3</Height></Size></DYMORect><LabelObjects>
  ${obj("TextObject", "Company", 0.1, 0.06, 3.0, 0.4, span("Sample Company", 20, true))}
  ${obj("TextObject", "Ticket", 0.1, 0.5, 3.0, 0.3, span("Ticket#: 12345", 16, false))}
  ${obj("BarcodeObject", "Barcode", 0.1, 0.85, 2.4, 0.4, "<BarcodeFormat>Code128Auto</BarcodeFormat><Data><DataString>12345</DataString></Data>")}
  ${obj("ImageObject", "Logo", 2.6, 0.75, 0.55, 0.45, `<ScaleMode>Uniform</ScaleMode><Image>${PIXEL}</Image>`)}
  </LabelObjects></DYMOLabel></DesktopLabel>`;
setTimeout(async () => {
  const out = {};
  out.c128_width_errors = C128.filter((p, i) => [...p].reduce((s, d) => s + +d, 0) !== (i === 106 ? 13 : 11)).length;
  const f = (customer, barcode) => ({ customer, received: "2026-09-30", ticket: "75013", barcode });
  const tag = (fields, offset = 0, tpl = null) => drawTag(document.createElement("canvas"), fields, false, offset, tpl).toDataURL();
  out.tag = tag(f("Acme Dental Group", false));
  out.long_bar = tag(f("Jonathan Worthington-Smythe Orthodontics", true));
  out.contact_bar = tag({ ...f("Acme Dental Group", true), contact: "Jane Smith" });
  out.home_bar = tag({ ...f("Jane Smith", true), contact: "Jane Smith" });                 // a home customer: name once
  out.offset_bar = tag(f("Acme Dental Group", true), 1.0);                    // text position +1 mm: everything moves down
  const tpl = parseDymo(DYMO, "harness.dymo"); await templateImagesReady(tpl);
  out.template_images = tpl.objects.filter(o => o.kind === "image").length;
  out.template_bar = tag(f("Acme Dental Group", true), 0, tpl);
  out.blank = tag({ free: "FRAGILE\nScreen cracked" });
  // intake: serial + bin line; an accessory tag; the device tag of a set with a long name and a contact (the fullest tag)
  out.intake_bar = tag({ ...f("Acme Dental Group", true), serial: "PF3XK2LQ", bin: "B3", part: "1 of 3" });
  out.accessory_bar = tag({ ...f("Acme Dental Group", true), item: "Charger", part: "2 of 3" });
  // the designer: a 30336 label (1" × 2-1/8", text along it) with a Code 128, and an upright 4×6 with a QR + a box
  const st = (w, h, a) => ({ name: "x", stock: "x", page: "x", width_in: w / 72, height_in: h / 72, safe_in: a.map(v => v / 72) });
  const d30336 = { orientation: "Landscape", rect: { x: 0, y: 0, w: 1.89, h: 0.86 }, objects: [
    { kind: "text", x: 0.03, y: 0.02, w: 1.8, h: 0.3, halign: "Left", valign: "Middle", fit: "ShrinkToFit", lines: [{ size: 14, bold: true }], format: "{company}" },
    { kind: "barcode", x: 0.05, y: 0.4, w: 1.75, h: 0.42, halign: "Left", format: "{ticket}", symbology: "Code128Auto" }] };
  out.design_30336 = drawLabel(document.createElement("canvas"), st(72, 153.12, [4.08, 4.32, 69.12, 146.64]), d30336, f("Acme", true)).toDataURL();
  const d46 = { orientation: "Portrait", rect: { x: 0, y: 0, w: 3.99, h: 5.99 }, objects: [
    { kind: "shape", shape: "box", x: 0.1, y: 0.1, w: 3.7, h: 5.7, stroke: 0.03 },
    { kind: "text", x: 0.3, y: 0.3, w: 3.3, h: 0.8, halign: "Center", valign: "Middle", fit: "ShrinkToFit", lines: [{ size: 36, bold: true }], format: "{company}" },
    { kind: "barcode", x: 1.0, y: 1.5, w: 2.0, h: 2.0, halign: "Left", format: "https://example.com/t/{ticket}", symbology: "QRCode" }] };
  out.design_4x6 = drawLabel(document.createElement("canvas"), st(295.92, 451.92, [4.08, 4.08, 292.08, 436.08]), d46, f("Acme", true)).toDataURL();
  out.full_bar = tag({ ...f("Jonathan Worthington-Smythe Orthodontics", true), contact: "Jane Smith", serial: "5CD1234XYZ", bin: "Shelf 4" });
  // the same template with a Code 39 barcode, and with a DYMO QR object instead (web/barcodes.js through drawTemplate)
  const c39 = parseDymo(DYMO.replace("Code128Auto", "Code39"), "c39.dymo"); await templateImagesReady(c39);
  out.template_c39 = tag(f("Acme Dental Group", true), 0, c39);
  const qrx = DYMO.replace(/<BarcodeObject>.*?<\/BarcodeObject>/s,
    obj("QRCodeObject", "QR", 0.1, 0.75, 0.5, 0.5, "<Data><DataString>12345</DataString></Data>"));
  const qrt = parseDymo(qrx, "qr.dymo"); await templateImagesReady(qrt);
  out.template_qr = tag(f("Acme Dental Group", true), 0, qrt);                // blank tag: click the preview and type
  document.body.innerHTML = "<pre id=out>" + JSON.stringify(out) + "</pre>";
}, 1500);
