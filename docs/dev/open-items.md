# LabelDesk — open items (tick them off here)

## Open items (verify at work, with the real printers)
- [ ] Printers' IPs; is raw port **9100** open and does the status handshake work over it? (`tools/add-printers.sh` warns
      if the port doesn't answer.) If 9100 doesn't work, check the printer's web page / `avahi-browse -rt _ipp._tcp` for IPP.
- [ ] First real tag: text direction vs feed — if upside down, tick "Rotate 180°" (stored per browser) or set
      `flip_tag` in config.json.
- [x] Tag roll confirmed 2026-10-08: **30252 Address, 1-1/8" × 3-1/2"**. On 0.7.0 (30321 layout) the top line printed off the
      label's edge. 0.7.1 adds 30252 (PPD w79h252, ImageableArea 4.32 4.32 76.08 235.44 → 298×962) as the default; 30321
      stays in Settings → Tag labels. Rendered + barcodes checked headless; NOT yet printed on the real roll.
- [ ] Match the tag to the owner's existing `.dymo` template (`Asset Tag.dymo`, seen 2026-10-01 on a Windows PC at work):
      LabelName **Address** (= 30252, 1-1/8" × 3-1/2", NOT 30321 — confirm the roll), Landscape, printable rect
      0.23/0.06 + 3.21 × 0.997 in. Objects (Segoe UI, none bold, left): customer name 20.7 pt AlwaysFit · "Date Recieved:"
      16 pt · date ("August 21, 2024") 14.5 pt · "Ticket #:" 19.2 pt · shop logo ImageObject @2.88,0.67 0.56×0.34.
      Done: the logo (web/tag-logo.png) bottom-right of the BUILT-IN tag, 0.42" tall, thresholded to black/white.
      Imported templates don't draw images yet, so an imported Asset Tag.dymo would print without the logo.
- [ ] Shipping: print one real UPS PDF page, one FedEx PDF page and one screenshot; check each barcode scans and the
      label is upright (the app warns when a screenshot is < ~170 dpi at label size).
- [ ] Does each printer advertise itself by name (dnssd)? add-printers.sh prefers that; otherwise give them DHCP
      reservations in the router.
- [ ] Print dialog: in Firefox/Chrome, print a carrier label page to "Shipping Label (LabelDesk)" → opens in LabelDesk.
- [ ] ConnectWise: the ConnectWise admin creates the role/API member/Client ID (docs/connectwise-setup.md); Test connection; check a
      residential ticket (company may be a catch-all — is the contact the better "company" there?).
- [x] Windows 11 build — tested 2026-09-30 in the Windows 11 VM with DYMO Connect 1.5.1.20 drivers + fake LabelWriter:
      install, ConnectWise (fake), tag + UPS 4×6 print (decoded output correct), Downloads pickup, History, Settings.
- [ ] Rollout: share installs by link (email template: docs/install-email.txt). Gmail blocks the zips as attachments.
- [ ] Windows at work: install dist/LabelDesk-0.5.0.msi on a coworker PC that already has DYMO Connect + both printers.
- [ ] Owner approval for ConnectWise: LabelDesk must work fully without it (it does — off/invisible by default);
      show him docs/connectwise-setup.md "What LabelDesk does and doesn't do". Enable per PC via …/#connectwise.
- [ ] Dev PCs: test queues may point at socket://127.0.0.1:9100 — start `tests/fake_labelwriter.py /tmp/ldjobs` to test prints.
- [ ] Tag text position (↑/↓ 0.25 mm, per PC; 2026-10-03) — set it on the Fedora PC where the top of the name clipped; try +0.5 mm first.
- [x] Merged 0.5.1 (logo, Windows printers by driver name) with 0.5.0+offset+templates → **0.6.0** (2026-10-08). Offset now
      moves the whole built-in design incl. the logo (at +3 mm the logo's bottom edge can clip — it's what the printer does).
      Render-checked headless (sizes + barcodes, built-in/offset/template); NOT yet printed on a real or fake printer.
- [ ] 0.6.0 update check + tools/update.sh: first real run once the repo is public (raw VERSION needs a public repo).
- [~] Windows updates: Actions builds the MSI per tag + one-click Install update (0.7.0). MSI build verified with Ubuntu's
      wixl (stand-in Python zip); the workflow itself and Install update have NOT run yet (needs the public repo + a Windows PC).
- [ ] Shop logo is per PC since 0.7.0: on each PC, Settings → Tag logo → choose the shop's logo file once.
- [ ] Labels remaining: unknown whether the 550's status carries a count (DYMO's driver reads only bytes 0-4, 8, 10, 21).
      At work: tools/dymo-status.py <ip> --save a.json, print N labels, --compare a.json. Build the display only if a byte
      drops by exactly N.
- [ ] Blank tag (click the preview and type) built 0.7.0 from a description of another technician's local version — compare with theirs.
- [ ] Windows PC on Wi-Fi couldn't add the printers (reported, cause NOT known yet). On that PC: run
      windows/printer-check.ps1 -PrinterIP <550T>,<5XL> and decide from its output (SETUP.md §3). Both scripts are
      parse-checked and the port/subnet logic tested in PowerShell 7 on Linux; NOT yet run on Windows.
- [ ] Fedora PCs installed from zips: move each to a git clone (README → Install) so update.sh works there.
- [~] **.dymo template import** — BUILT 2026-10-03 (web/template.js: Layout menu, Import .dymo… / drop on the preview,
      {company} {customer} {received} {ticket} field patterns, offset + Rotate 180° apply). Tested with a synthetic 30321 template in
      DYMO's format (render + barcode scan). Still open: the owner's real template (acceptance), shapes/images aren't drawn.
- [~] Template pictures (ImageObject, found by base64 content) drawn since 0.7.0; tested with a synthetic template —
      check against the real Asset Tag.dymo.
- [ ] (original spec) **.dymo template import (required by the owner, 2026-09-30):** open/drop a DYMO Connect `.dymo` file → LabelDesk
      renders it itself at 300 dpi (preview = print) and maps its text/barcode objects to Company / Customer name /
      Received / Ticket # (guess from object names or sample text, user confirms); templates selectable per PC. Format
      (checked on dymosoftware/DCD-SDK-Sample `samplelabel.dymo` + public files): XML `DesktopLabel > DYMOLabel` with
      `Orientation`, `LabelName`, `LabelObjects` (TextObject / AddressObject / BarcodeObject / ImageObject / Shape…),
      each with `ObjectLayout` `DYMOPoint X/Y` + `Size Width/Height` in INCHES, fonts in points, `BarcodeFormat` e.g.
      `Code128Auto`. Test fixtures: DYMO's SDK samples; acceptance = the owner's own tag template (not seen yet).
- [ ] Later: general label designer (text/barcode/QR/image objects, templates per size), `.dymo` import, CSV batch.
- [ ] **macOS on the real printers**: CI proves the Mac driver path against the fake LabelWriter; print a tag (long name +
      barcode) and a real UPS label from a Mac in the shop, scan both. Check DYMO Connect for Mac's CURRENT version has
      the same lw550t/lw5xl PPDs (CI uses 1.4.3.103, the newest downloadable by URL).

## Roadmap (2026-10-10 review: as good as DYMO Connect, then better) — pick one, ship it, tick it
**Owner's decision 2026-10-10:** build 1–5, 7, 9–11 and the MSP intake/lookup items (accessory tags, intake tag,
"been here before?", bench/pickup scan). **Not wanted:** 6 signed Windows installer (skipped for now — unsigned is
fine), 8 scanner-first auto-print, the customer claim receipt, and all deployment/lifecycle items (don't fit the
shop's workflow). 11 = an UNSIGNED .pkg (no Apple Developer account).
**1** and **2** built in 0.9.0 (CI + fakes on Fedora and macOS); still to check against the shop's REAL printers.
- [~] 1. **Printers found automatically** — Fedora: own mDNS scan (IPs → rolls). **Mac: through CUPS** (`lpinfo --include-
      schemes dnssd`; macOS Local Network privacy blocks the LaunchAgent's own scan — "No route to host", CI 2026-10-10);
      queues by dnssd:// URI, so no rolls on the Mac unless a queue has an IP. **Windows: system DNS-SD** (server/winmdns.py,
      DnsServiceBrowse/Resolve, checked on the Win11 VM with announced fakes: found, rolls read); offers only (UAC).
      Open: Windows shows the shop's DYMO Connect printers' matches as "extra" (the Windows port's IP isn't read yet);
      real printers: do they announce _pdl-datastream on Bonjour?
- [~] 2. **Loaded roll from the printer** (0.9.0; real printers: `tools/dymo-status.py <ip>` — SKU text + count as documented?) (550 series NFC, status bytes 11–22 SKU, 27–28 labels left; ESC U = size in mm):
      pick 30252/30321 automatically, warn before printing on the wrong roll, labels remaining + low warning.
- [ ] 3. More barcodes: Code 39, UPC next to Code 128; **QR only for phones** (customers), see note below.
      **Shop scanner = 1D barcode scanner only (no QR reader, 2026-10-10):** everything a technician scans (ticket #,
      asset #, serial) must be Code 128. QR is for customers' phones only (support link on deployment tags). A 2D
      scanner (reads both) is a cheap upgrade if QR is ever wanted in-house.
- [ ] 4. **Label designer**: any DYMO size; text/barcode/QR/image/shape objects; templates shared via the repo (no work data).
- [ ] 5. **Spreadsheet batch**: CSV/Excel in, one label per row, field mapping.
- [–] (not wanted) 6. **Signed Windows installer** (no SmartScreen "unknown publisher").
- [ ] 7. Hands-free shipping (opt-in): a carrier label in Downloads prints itself once its barcode checks out.
- [–] (not wanted) 8. Scanner-first: scanning a ticket barcode fills the ticket # and prints.
- [ ] 9. Searchable history (tracking #, customer, serial, ticket) + export.
- [ ] 10. Self-healing: auto-resume paused queues; printer panel (media, errors, labels left).
- [ ] 11. Mac installer package for people who don't use Terminal.

## MSP ideas: asset tags for drop-off repairs and customer deployments (brainstorm, 2026-10-10)
Intake (PC dropped off for repair):
- [ ] **Intake tag preset**: ticket # · customer/company · received date · **serial** · **bin/shelf** · QR/Code 128 of the
      ticket (Code 128 — the shop's scanner is 1D). A USB barcode scanner reads the serial sticker on the laptop straight into the Serial field.
- [ ] **"1 of 3" accessory tags** with the same ticket # (charger, dock, bag) — one click prints the set.
- [–] (not wanted) **Customer claim label/receipt** on the 5XL: ticket #, what was left (device, accessories, password given?), ticket #
      as Code 128 for the pickup scan.
- [ ] **Been here before?** ConnectWise configuration lookup by serial (read-only) → previous tickets for this device.
- [ ] **Bench scan**: scanning a tag in LabelDesk opens the ticket (ConnectWise link) and the tag's history; pickup scan marks
      it collected in History.
Deployment + lifecycle items: **not wanted** (owner, 2026-10-10) — removed.

