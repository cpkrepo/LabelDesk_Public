# LabelDesk — open items (tick them off here)

## Open items (verify at work, with the real printers)
- [ ] Printers' IPs; is raw port **9100** open and does the status handshake work over it? (`tools/add-printers.sh` warns
      if the port doesn't answer.) If 9100 doesn't work, check the printer's web page / `avahi-browse -rt _ipp._tcp` for IPP.
- [ ] First real tag: text direction vs feed — if upside down, tick "Rotate 180°" (stored per browser) or set
      `flip_tag` in config.json.
- [ ] Confirm the tag roll is 30321 (1.4 × 3.5). If it's another size, add it to `LABELS` in server/app.py from the PPD
      (`*PageSize` + `*ImageableArea` lines in /usr/share/cups/model/lw550t.ppd*).
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
