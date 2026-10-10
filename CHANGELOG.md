# What's new in LabelDesk

Newest first. Every version is on the [Releases page](https://github.com/cpkrepo/LabelDesk_Public/releases) (Windows
installer attached) and any of them can be brought back with `tools/rollback.sh <version>`.

**Changing LabelDesk?** Add a line under `## Unreleased` describing what changed for the people using it;
`tools/update.sh` turns that heading into the version number when it publishes.

## Unreleased
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
