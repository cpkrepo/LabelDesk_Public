# LabelDesk on macOS

Same model as Fedora: a git clone in `~/LabelDesk_Public`, CUPS queues `Dymo-550-Turbo` / `Dymo-5XL`, `tools/update.sh`.
Built 2026-10-10. Proven in CI on a real Mac (`.github/workflows/macos.yml`) with DYMO's driver and the fake LabelWriter;
**not yet printed on the shop's real printers from a Mac** (open item).

## Facts
- **Driver = DYMO Connect for Mac** (`/Library/Printers/PPDs/Contents/Resources/lw550t.ppd.gz`, `lw5xl.ppd.gz`, filter
  `/Library/Printers/DYMO/Filters/V2/raster2dymolw`, universal x86_64 + arm64). Its PPDs have the **same page names,
  PaperDimension and ImageableArea** as DYMO's Linux driver (diffed 2026-10-10 against DCDMac 1.4.3.103), so
  `LABELS` / canvas sizes in app.py are shared. No SELinux, no driver build.
- **Printing = an exact-size PDF**, not the PNG: the page sends grey pixels (as for Windows) and `label_pdf()` wraps them
  in a one-page PDF of the label's page size, image at 300 dpi centred in the ImageableArea (where Fedora's
  `-o ppi=300 -o position=center` puts the PNG). macOS's own image filters don't promise to honour ppi/position.
  Checked on Fedora's CUPS + DYMO driver: PDF and PNG paths land within 1 dot of each other (tag 304×963 vs 304×962;
  4×6 1200×1800 vs 1200×1798).
- Python = Apple's `/usr/bin/python3` (3.9, from `xcode-select --install`) — keep the server 3.9-compatible. Shell
  scripts run on bash 3.2: no `mapfile`, `timeout`, `stat -c`, `readlink -f`, GNU `sed -i` (tools/mac/common.sh has
  `with_timeout` and `answers`). CI runs the unit tests (incl. update.sh/rollback.sh) on both.
- App = LaunchAgent `~/Library/LaunchAgents/com.labeldesk.app.plist` (log `~/Library/Logs/LabelDesk.log`) +
  `~/Applications/LabelDesk.app` (opens Chrome/Edge/Brave `--app`, else the default browser). Data + config:
  `~/Library/Application Support/LabelDesk`. Keys: login Keychain, generic password "LabelDesk ConnectWise" (base64
  JSON; written through `security -i` on stdin, never argv).
- Update now: `tools/update.sh` in its own session (survives launchd restarting LabelDesk); update.sh re-runs
  tools/install-app.sh when the LaunchAgent exists.
- Not on the Mac: the "Shipping Label (LabelDesk)" print-dialog printer (CUPS backends live under SIP) — Save as PDF to
  Downloads instead; pdftotext (the browser checks downloaded PDFs, as on Windows); zbar is optional (`brew install zbar`).
