# LabelDesk — printers, labels, what it replaces

DYMO label printing on **Fedora** for the shop, replacing DYMO Connect (Windows/macOS only). Runs on the work Fedora
PC; opens in the browser at http://127.0.0.1:8792 ("LabelDesk" in the app menu). Developed on a separate
Fedora 44 PC (same release as work) without the real printers; the first real print happens at work.

## The shop's printers and labels (facts — don't reinterpret)
| Printer | Connection | Job | Stock | CUPS queue / page |
|---|---|---|---|---|
| DYMO LabelWriter **550 Turbo** | Ethernet | inventory tags | **30252 Address, 1-1/8" × 3-1/2"** (measured 2026-10-08; 30321 selectable in Settings) | `Dymo-550-Turbo` / `w79h252` |
| DYMO LabelWriter **5XL** | Ethernet | shipping labels (mostly UPS) | 1744907, 4" × 6" | `Dymo-5XL` / `1744907_4_in_x_6_in` |

- **Inventory tag** = three typed lines: customer name · `Received: MM/DD/YYYY` · `Ticket#: 75013`. Everything is typed
  by hand (no ticket system to look up). Optional Code 128 barcode of the ticket number.
- **Shipping** = the UPS label is screenshotted and pasted (today they paste the image into DYMO Connect). LabelDesk
  takes paste / drop / open (PNG, JPG, PDF), trims, rotates and fits it to 4 × 6.
- The owner **has an existing DYMO Connect template for the tag** (a `.dymo` file) at work — not yet seen. When it
  shows up, match LabelDesk's tag to it (see the `dymo-template-import` skill) instead of guessing at fonts/positions.
