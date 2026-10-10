# LabelDesk — code layout

## Layout
```
server/app.py        stdlib HTTP server: /api/print (PNG → lp; ship labels barcode-checked first; double press → 409),
                     /api/job/<id> (followed via IPP until done/failed; failed jobs are cancelled), /api/printers
                     (+ /resume), /api/history (+ /<id>/image), /api/reprint/<id>, /api/customers, /api/inbox, /api/pdf.
                     SQLite ~/.local/share/labeldesk/labeldesk.db (+ ship/<id>.png, last 200). Config: env or
                     ~/.config/labeldesk/config.json (tag_queue, ship_queue, bind, port, flip_tag, tag_offset_mm,
                     watch_downloads, update_check, update_url). /api/update: newest VERSION on GitHub (asked after
                     each print, cached 60 s) + canUpdateNow; POST /api/update/run (Fedora, no local changes:
                     systemd-run tools/update.sh), /api/update/install (Windows: release MSI, sha256-checked, msiexec /qb).
                     Windows Settings: /api/windows/printer-check, /api/windows/add-dymo. The version lives ONLY in ./VERSION (app.py + build-windows.sh read it)
server/dymo.py       straight to the printers (stdlib): Bonjour browse (mDNS legacy-unicast query), ESC A 0 status,
                     ESC U roll info (DYMO 550 Tech Ref byte layouts), roll → stock (SKU or size)
server/autoprint.py  printers set themselves up: scan at start + every 5 min → add missing queue / re-point a moved printer
                     (only when unambiguous; else offers), events for the page, the roll per printer (cached 30 s, never
                     while busy); app.py QueueOps = lpstat/lpadmin; roll_check() stops prints on the wrong/empty roll (422)
server/sheet.py      Batch → Open spreadsheet: CSV (sniffed delimiter, BOM, cp1252) + .xlsx (zip/XML, first sheet, date formats →
                     ISO), stdlib; POST /api/sheet. Sample: tests/samples/intake.xlsx (LibreOffice-made, made-up data)
server/winmdns.py    Windows: Bonjour via the system's DNS-SD (dnsapi DnsServiceBrowse/Resolve/Register, ctypes) — no firewall rule
                     needed; tests/windows/mdns_check.py proves it on Windows (announces fakes, finds them)
server/ipp.py        minimal IPP client for local CUPS (job + printer state) and DYMO reasons → plain English
server/barcode.py    zbarimg on the print image: UPS 1Z…, FedEx 34-digit (last 12 = tracking #), USPS
server/inbox.py      watches Downloads (new carrier PDFs only) + /var/spool/labeldesk (the print-dialog printer)
server/connectwise.py  read-only ConnectWise PSA lookups (ticket → company/contact; configurations). Cloud NA.
server/keys.py       API keys: Fedora login keyring (secret-tool) · Windows DPAPI · 0600 file fallback
docs/connectwise-setup.md  for the ConnectWise admin: read-only role, API member + keys, Client ID
tests/fake_connectwise.py  stand-in ConnectWise API (tests + trying the UI without keys)
web/designer.js      Designer tab: layouts for any stock (template.js format + stock/orientation/flip; shapes), drag/resize, per PC
                     (localStorage) or the shop's (templates/*.json via POST /api/templates/share → update.sh → PR); prints
                     with app.drawLabel + /api/print {stock} (server stock_label: page + printable area from stocks.json)
server/stocks.json   65 DYMO labels from DYMO's lw550t/lw5xl PPDs (tools/gen-stocks.py regenerates it)
web/barcodes.js      Code 128 / Code 39 / UPC-A / EAN-13 / QR encoders + draw (whole-pixel modules); tests/barcodes.test.mjs
                     decodes each with zbarimg; render_check.sh decodes them on real tags
web/                 index.html · app.js (canvas rendering at 300 dpi, Code 128 encoder, shipping crop/turn, history) ·
                     detect.js (finds the label on a carrier page + which way is up) · template.js (.dymo import +
                     render, incl. embedded pictures) · style.css. Shop logo: per PC in the config folder
                     (GET/POST /api/logo, /api/logo/clear), migrated once from an old web/tag-logo.png
tools/mac/build-pkg.sh    unsigned payload-free .pkg (pkgbuild, on a Mac): postinstall = clone for the console user + install-app;
                          CI builds + installs it on every PR, attaches it to every release (macos.yml job pkg)
tools/mac/                macOS: install-all · add-printers (DYMO Connect for Mac's PPDs) · install-app (LaunchAgent +
                          ~/Applications/LabelDesk.app) · doctor — tools/install-all|add-printers|install-app|doctor.sh exec these on Darwin
tools/install-driver.sh   builds + installs DYMO's official 550-series CUPS driver, + SELinux module
tools/selinux/dymo_cups.te
tools/add-printers.sh     the two DYMO queues (by name via dnssd if found, else socket://IP:9100) + the
                          "Shipping Label (LabelDesk)" print-dialog printer (tools/cups/labeldesk backend, spool
                          /var/spool/labeldesk 1777, SELinux print_spool_t)
tools/doctor.sh           health check (driver, SELinux, CUPS queues, printers answering, app); --fix repairs safe things
tools/install-app.sh      systemd --user service + app-menu entry (run from the checkout; update.sh re-runs it)
tools/dymo-status.py      READ-ONLY 32-byte status of a networked 550/5XL (ESC A 0); --save/--compare to find a label counter
.github/workflows/macos.yml  every push: unit tests on macOS's python3 3.9 + bash 3.2, DYMO Connect for Mac, install-all.sh, print_check.py
.github/workflows/windows-installer.yml  on tag v*: unit tests, tools/build-windows.sh, MSI + .sha256 → GitHub release
tools/package-skills.sh   .claude/skills → dist/skills/<skill>.zip for Claude.ai upload (checks name/description limits)
windows/printer-check.ps1 READ-ONLY Windows network/printer diagnostic (Wi-Fi vs wired, Public profile, tcp 9100, drivers)
windows/add-dymo-printer.ps1  add/remove a DYMO printer by IP (raw 9100 + DYMO Connect's driver); admin; both go in the MSI
tools/switch-version.sh   Settings → Version (Fedora/Mac): this PC to v<x> (git reset to the tag; config hold_version = no update
                          notices) or newest; --everyone (owner) → rollback.sh. Windows: app.py install_windows_version (older =
                          uninstall first). Owner = GitHub admin or git config labeldesk.publisher true (update.sh, rollback.sh, app.py)
tools/rollback.sh         list versions / publish an older version's code as the next version (rulesets forbid force-push + tag deletion)
tools/update.sh           commit this PC's changes → rebase on GitHub main → bump VERSION → tests → push + tag → restart
tests/test_server.py      unit tests (no printer): python3 -m unittest discover -s tests
tests/test_autoprint.py   status/roll bytes, Bonjour answers, every auto-setup decision (fake ops; no network)
tests/auto_check.py       end-to-end: a RUNNING LabelDesk with no queues + fakes announcing on Bonjour → queues added, rolls read
tests/test_mac_paths.py   macOS paths run anywhere: grey → exact-size PDF for lp, Update now without systemd, Keychain
tests/print_check.py      end-to-end: print a tag + 4×6 pattern through a RUNNING LabelDesk to the fake printer, check size/margins/orientation
tests/test_rollback.py    tools/rollback.sh against the same throwaway repos
tests/test_update.py      tools/update.sh against a throwaway bare repo + two clones (no network)
tests/render_check.sh     headless-Chrome render + zbarimg barcode check (built-in tag, logo, offset, imported template)
tests/browser_check.sh    real Chrome on Xvfb: pdf.js opens a PDF, a label saved to Downloads opens by itself, no page errors
tests/fake_labelwriter.py stand-in network LabelWriter (answers the status handshake, decodes jobs to PBM)
tests/detect.test.mjs     label detection on synthetic carrier pages: node --test tests/
tests/render/ship.js      browser harness: synthetic page → findLabel → drawShip (turn + crop wiring)
```
The browser draws the label; the server only prints the PNG. **The preview is the print** — keep it that way.
