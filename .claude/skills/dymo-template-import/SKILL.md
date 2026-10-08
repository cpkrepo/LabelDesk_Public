---
name: dymo-template-import
description: Match LabelDesk's inventory tag (or add a label type) to a DYMO Connect .dymo or DYMO Label .label template. Use when given a .dymo/.label file or asked to copy a DYMO design.
---

# Importing / matching a DYMO template

The owner has a DYMO Connect template for the inventory tag. Goal: LabelDesk's tag matches it (same text, fonts,
sizes, positions, barcode) — or, later, a general `.dymo` importer.

1. **Read the file, don't assume the schema.** `.dymo` (DYMO Connect) and `.label` (older DYMO Label v8) are XML.
   Pretty-print it (`python3 -c "import xml.dom.minidom,sys;print(xml.dom.minidom.parse(sys.argv[1]).toprettyxml())" f.dymo`)
   and identify: the label/paper name (the shop's tags are 30252 Address; 30321 Large Address is the other supported tag stock), the page size and orientation, and each object
   (text, address, barcode, image, shape) with its position, size, font name/size/bold, alignment, and any fixed text.
2. **Work out the units from the file itself**: compare the declared label dimensions to 1-1/8" × 3-1/2" (30252) and 1.4" × 3.5" (30321). Older
   `.label` files use twips (1/1440 in); check rather than assume for `.dymo`.
3. **Map to LabelDesk**: the tag is drawn in `drawTag()` (web/app.js) in a design space of the tag label's printable area turned sideways (30252: 962 × 298 px;
   30321: 960 × 391) at 300 dpi (≈ 3.2" × 1.3"). Convert inches → px (×300), subtract the printable-area offset from the
   PPD (`*ImageableArea w79h252 … "4.32 4.32 76.08 235.44"` for 30252, in points), keep text inside the design space.
   Fonts: use the template's font if installed (`fc-list | grep -i <name>`); otherwise the closest installed one and say so.
   Keep fields bound to the form (customer / received / ticket) — the template's sample text is just placeholders.
4. **Verify**: `tests/render_check.sh`, compare `render-out/tag-reading.png` side by side with a DYMO Connect
   screenshot/print of the template; then a real print at work.
5. Record in CLAUDE.md what the template specified (fonts, sizes, positions) and tick the open item.
