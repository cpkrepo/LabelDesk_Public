// Render harness: draws sample labels with the real app code and dumps them as PNG data URLs into the page.
import { drawTag, C128 } from "./app.js";
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
  out.offset_bar = tag(f("Acme Dental Group", true), 1.0);                    // text position +1 mm: everything moves down
  const tpl = parseDymo(DYMO, "harness.dymo"); await templateImagesReady(tpl);
  out.template_images = tpl.objects.filter(o => o.kind === "image").length;
  out.template_bar = tag(f("Acme Dental Group", true), 0, tpl);
  out.blank = tag({ free: "FRAGILE\nScreen cracked" });                // blank tag: click the preview and type
  document.body.innerHTML = "<pre id=out>" + JSON.stringify(out) + "</pre>";
}, 1500);
