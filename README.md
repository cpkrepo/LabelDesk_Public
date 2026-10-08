# LabelDesk

Print DYMO labels from **Fedora** or **Windows 11**: a replacement for DYMO Connect built for a repair shop.

- **Inventory tags** on the LabelWriter **550 Turbo** (30321, 1.4" × 3.5"): type the ticket # (with **ConnectWise**
  connected, the company and customer name fill in; setup for the admin in `docs/connectwise-setup.md`), optional
  barcode of the ticket number, Enter to print, batch printing, reprint from history. Or import your own DYMO Connect
  `.dymo` tag template (Layout → Import .dymo…; pictures in it print too). **Blank tag:** click the preview and type
  any text (Ctrl+Enter prints). Your shop logo goes on the tag from Settings → Tag logo (kept per PC, not in this repo).
- **Shipping labels** on the LabelWriter **5XL** (4" × 6"): paste a screenshot (Ctrl+V) or drop the carrier's PDF.
  The label is found (UPS and FedEx pages), turned upright and fitted; adjust with ↺ ↻ 180° or by dragging a box.
- The preview is exactly what prints (drawn at the printers' 300 dpi).

**Technicians: the full guide is [SETUP.md](SETUP.md)** (install, printers on Wi-Fi, Claude Code and the skills,
GitHub access, shipping changes, Windows releases, uninstalling).

## Install on Fedora (once per PC)
```bash
git clone https://github.com/cpkrepo/LabelDesk_Public.git ~/LabelDesk_Public && cd ~/LabelDesk_Public
tools/install-all.sh                         # driver + printers (found by name) + app + health check
#   = tools/install-driver.sh · tools/add-printers.sh [<550-Turbo-IP> <5XL-IP>] · tools/install-app.sh · tools/doctor.sh
```
Open **LabelDesk** from the app menu (or http://127.0.0.1:8792). Already running LabelDesk from an unzipped folder?
Clone as above and run `tools/install-app.sh` from the clone; the app then runs from the clone (history and settings
are kept, they live in your home folder). Delete the old folder afterwards.

## Windows 11
Run **LabelDesk-<version>.msi** (from the Releases page, or `tools/build-windows.sh` on Fedora). No admin rights needed;
it prints through the DYMO driver that **DYMO Connect** already installed. Start menu → **LabelDesk**.
Printers not found (often on Wi-Fi)? `printer-check.ps1` and `add-dymo-printer.ps1`: SETUP.md section 3.

## Updates
After every print LabelDesk asks GitHub for the newest version number (one small file; nothing about your labels is
sent). If there's a newer one it shows a notice:
- **Fedora:** click **Update now** (when this PC has no changes of its own), or run `tools/update.sh` in the clone,
  which keeps anything changed on this PC: commits it, merges it onto the
  newest version, raises the version, runs the tests and pushes it back to GitHub, then restarts LabelDesk. If both
  sides changed the same lines it stops without changing anything and says so. New files that aren't source code
  (PDFs, images, .dymo, databases) are never committed: the repo is public.
- **Windows:** click **Install update**. LabelDesk downloads the new installer from the GitHub release, checks its
  SHA-256, installs it (no admin) and restarts. GitHub builds that installer by itself for every new version.

Turn the check off with `"update_check": false` in `~/.config/labeldesk/config.json` (Windows: `%APPDATA%\LabelDesk\config.json`).

## Changing LabelDesk with Claude
Open Claude Code in the clone. It reads `CLAUDE.md` and the skills in `.claude/skills/` (printer setup, testing,
DYMO template import) and ships each change through `tools/update.sh`. Pushing needs write access to this repo and
a signed-in PC (SETUP.md section 5). For Claude.ai chat, `tools/package-skills.sh` makes uploadable skill ZIPs.

## If something doesn't print
`tools/doctor.sh` checks everything and says what's wrong (`--fix` repairs what's safe). More in
`.claude/skills/labeldesk-printer-setup/SKILL.md`.

## Development
`python3 -m unittest discover -s tests` · `node --test tests/*.mjs` · `tests/render_check.sh` · `tests/browser_check.sh`.
Standard-library Python + plain JS, no build step, no third-party packages. Code map: `docs/dev/layout.md`.

## License
MIT (see [LICENSE](LICENSE)). No shop logo is included; each PC sets its own in Settings.
Uninstall: `tools/install-app.sh --remove` (Fedora) or Settings → Apps (Windows).
