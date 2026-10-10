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
server/ipp.py        minimal IPP client for local CUPS (job + printer state) and DYMO reasons → plain English
server/barcode.py    zbarimg on the print image: UPS 1Z…, FedEx 34-digit (last 12 = tracking #), USPS
server/inbox.py      watches Downloads (new carrier PDFs only) + /var/spool/labeldesk (the print-dialog printer)
server/connectwise.py  read-only ConnectWise PSA lookups (ticket → company/contact; configurations). Cloud NA.
server/keys.py       API keys: Fedora login keyring (secret-tool) · Windows DPAPI · 0600 file fallback
docs/connectwise-setup.md  for the ConnectWise admin: read-only role, API member + keys, Client ID
tests/fake_connectwise.py  stand-in ConnectWise API (tests + trying the UI without keys)
web/                 index.html · app.js (canvas rendering at 300 dpi, Code 128 encoder, shipping crop/turn, history) ·
                     detect.js (finds the label on a carrier page + which way is up) · template.js (.dymo import +
                     render, incl. embedded pictures) · style.css. Shop logo: per PC in the config folder
                     (GET/POST /api/logo, /api/logo/clear), migrated once from an old web/tag-logo.png
tools/install-driver.sh   builds + installs DYMO's official 550-series CUPS driver, + SELinux module
tools/selinux/dymo_cups.te
tools/add-printers.sh     the two DYMO queues (by name via dnssd if found, else socket://IP:9100) + the
                          "Shipping Label (LabelDesk)" print-dialog printer (tools/cups/labeldesk backend, spool
                          /var/spool/labeldesk 1777, SELinux print_spool_t)
tools/doctor.sh           health check (driver, SELinux, CUPS queues, printers answering, app); --fix repairs safe things
tools/install-app.sh      systemd --user service + app-menu entry (run from the checkout; update.sh re-runs it)
tools/dymo-status.py      READ-ONLY 32-byte status of a networked 550/5XL (ESC A 0); --save/--compare to find a label counter
.github/workflows/windows-installer.yml  on tag v*: unit tests, tools/build-windows.sh, MSI + .sha256 → GitHub release
tools/package-skills.sh   .claude/skills → dist/skills/<skill>.zip for Claude.ai upload (checks name/description limits)
windows/printer-check.ps1 READ-ONLY Windows network/printer diagnostic (Wi-Fi vs wired, Public profile, tcp 9100, drivers)
windows/add-dymo-printer.ps1  add/remove a DYMO printer by IP (raw 9100 + DYMO Connect's driver); admin; both go in the MSI
tools/rollback.sh         list versions / publish an older version's code as the next version (rulesets forbid force-push + tag deletion)
tools/update.sh           commit this PC's changes → rebase on GitHub main → bump VERSION → tests → push + tag → restart
tests/test_server.py      unit tests (no printer): python3 -m unittest discover -s tests
tests/test_rollback.py    tools/rollback.sh against the same throwaway repos
tests/test_update.py      tools/update.sh against a throwaway bare repo + two clones (no network)
tests/render_check.sh     headless-Chrome render + zbarimg barcode check (built-in tag, logo, offset, imported template)
tests/browser_check.sh    real Chrome on Xvfb: pdf.js opens a PDF, a label saved to Downloads opens by itself, no page errors
tests/fake_labelwriter.py stand-in network LabelWriter (answers the status handshake, decodes jobs to PBM)
tests/detect.test.mjs     label detection on synthetic carrier pages: node --test tests/
tests/render/ship.js      browser harness: synthetic page → findLabel → drawShip (turn + crop wiring)
```
The browser draws the label; the server only prints the PNG. **The preview is the print** — keep it that way.
