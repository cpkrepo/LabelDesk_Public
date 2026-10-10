# What's new in LabelDesk

Newest first. Every version is on the [Releases page](https://github.com/cpkrepo/LabelDesk_Public/releases) (Windows
installer attached) and any of them can be brought back with `tools/rollback.sh <version>`.

**Changing LabelDesk?** Add a line under `## Unreleased` describing what changed for the people using it;
the owner's `tools/update.sh` turns that heading into the version number when it publishes.

## Unreleased
- **Hands-free shipping (opt-in, Settings → Shipping labels):** a UPS/FedEx/USPS label PDF that lands in Downloads
  prints by itself after a 5-second countdown you can cancel — only when the label was found, its tracking barcode
  scans, and that tracking # hasn't printed before. Anything uncertain waits for you, as before.
- **Intake tags:** optional **Serial #** (scan it off the laptop — the scanner's Enter moves on instead of printing) and
  **Shelf / bin**, printed on one small line and searchable in History.
- **Accessory tags:** list what came with the device (or tap Charger, Dock, Bag…) and LabelDesk prints the device tag
  ("1 of 3") plus one tag per accessory with the same ticket # and barcode. Imported templates can use {serial}, {bin}
  and {item} too.
- **More barcode types:** Code 39, UPC-A, EAN-13 and QR next to Code 128. Imported DYMO Connect templates now draw the
  barcode type they were made with (QR included); Settings → Tag barcode picks Code 128 or Code 39 for the ticket
  barcode. Everything a technician scans stays 1D; QR is for customers' phones.
- **History searches everything ever printed** on this PC — customer, ticket, serial, tracking number, any text — with
  filters for tags/shipping and dates, **Show more** for older labels, and **Export CSV** for Excel.
- **Paused printers resume by themselves** once they answer again (Fedora and Mac), and Settings → Printers shows each
  printer's state, roll and labels left.
- **Printers set themselves up** (Fedora; on the Mac, macOS doesn't allow it from the background yet, and on Windows it's
  untested — Settings says when it can't look). When LabelDesk starts and every few minutes it looks for the DYMO
  printers on the network: a printer it finds for the first time is set up, and a printer that got a new address is followed — no more
  `add-printers.sh` after a router restart. Other DYMO printers it finds are listed in Settings → Printers on the network
  with a "Use for…" button (Windows: always a button, it needs an admin prompt).
- **LabelDesk knows which roll is loaded** (550 Turbo and 5XL read the roll's chip): tags switch to 30252 or 30321 by
  themselves, the top bar shows the roll and how many labels are left, and printing on the wrong roll, an empty roll or
  with the cover open asks first instead of wasting labels.
- **Settings → Version:** every published version, with what changed in each. **Use this version** puts this PC on
  it — automatically, on Windows, Mac and Fedora — and keeps it there until **Back to the newest version**. On the
  owner's PC a "for every PC" box publishes it as the next version instead, so every PC goes back.
- **Windows: updating works again.** Installing a newer version over an older one could leave LabelDesk without its
  Python (it wouldn't start), and **Install update** never actually ran its installer. Both fixed and tested on Windows
  11; PCs on 0.8.1 or older need the 0.9.0 installer run by hand once.
- **Changes are approved by the owner.** Technicians' changes go to the owner as pull requests (`tools/update.sh` opens
  them); ideas, problems and rollback requests go in GitHub Issues. Only the owner publishes versions.

## 0.8.1 — 2026-10-10
- **Version history:** this file, linked from the README; every release on GitHub shows its version's notes.

## 0.8.0 — 2026-10-10
- **LabelDesk runs on macOS** (14 Sonoma or newer, Intel or Apple silicon). One Terminal line installs it after DYMO
  Connect for Mac: both printers are added, LabelDesk starts at login and is in Launchpad, **Update now** works.
  Labels print through DYMO's own Mac driver, exactly the size they print on Fedora and Windows.
- ConnectWise keys are kept in the Mac Keychain.
- Every change is now tested on a real Mac, including a print through DYMO's Mac driver.
- README: what LabelDesk is and how to install it on each system.

## 0.7.2 — 2026-10-10
- **Undo a bad version:** `tools/rollback.sh` (or ask Claude Code to "roll LabelDesk back") puts an older version back
  for every PC. GitHub now refuses changes that would erase the history.

## 0.7.1 — 2026-10-09
- Tags print on the shop's roll, **30252 Address (1⅛″ × 3½″)**, by default. 30321 Large Address can be chosen in
  Settings → Tag labels.

## 0.7.0 — 2026-10-08
- First version in this public repository: install with `git clone`, update in place, change it with Claude Code.
- **Blank tag:** click the preview and type any text.
- **Shop logo per PC** (Settings → Tag logo) — no logo in the repository.
- Pictures inside imported `.dymo` templates print too.

## 0.6 — 2026-10
- **Updates:** after each print LabelDesk checks for a newer version. Fedora: **Update now** / `tools/update.sh`
  (keeps and shares this PC's own changes). Windows: **Install update** (installer from the release, checksum-checked).
- Windows installers are built automatically for every version.
- **Import DYMO Connect templates** (`.dymo`) for the tag, with fields for company, customer, received date and ticket.
- Tag text position: nudge ↑/↓ in 0.25 mm steps per PC.

## 0.5.0 — 2026-09-30
- **Windows 11 version:** per-user installer, prints through the driver DYMO Connect installed, no admin rights.
- PDFs and barcode checks work in the browser (no extra tools on the PC).
- "Shipping Label (LabelDesk)" printer: print a carrier's page from any app straight into LabelDesk.
- Security and reliability pass: LabelDesk only answers on this PC, jobs can be cancelled, the date rolls over at
  midnight, downloads are recognised even when the browser back-dates them.

## 0.4.0 — 2026-09-30
- **ConnectWise (optional, read-only):** type a ticket number and the company and customer name fill in. Keys stay in
  the PC's keyring. Invisible unless it's set up and working.

## 0.3.0 — 2026-09-30
- Every job is followed until the printer has finished, with plain-English errors and **Resume** / **Print again**.
- Shipping labels' barcodes are checked before printing.
- History with tracking numbers, label images and reprint; customer name suggestions.

## 0.2.0 — 2026-09-30
- **Shipping labels from a full carrier page:** the label is found on UPS and FedEx pages, turned upright by its
  barcode, and can be adjusted (↺ ↻ 180°, drag a box).

## 0.1 — 2026-09-30
- First version: inventory tags on the LabelWriter 550 Turbo and 4″ × 6″ shipping labels on the 5XL from Fedora, with
  history; scripts for DYMO's driver, SELinux and the printer queues.
