# LabelDesk

**LabelDesk prints the shop's DYMO labels — inventory tags and 4″ × 6″ shipping labels — from Windows, macOS or
Fedora.** It replaces DYMO Connect with a small app built around what a repair shop actually prints: type a ticket
number and press Enter for a tag, or drop in a UPS/FedEx label and it comes out upright and the right size.

It runs entirely on your own computer, opens in your browser at http://127.0.0.1:8792, and prints straight to the two
network printers. No account, no server, nothing about your labels leaves the PC.

## What it does

- **Inventory tags** on the LabelWriter **550 Turbo** (30252 Address, 1⅛″ × 3½″; 30321 Large Address in Settings).
  Type the ticket number — with **ConnectWise** connected, the company and customer fill in by themselves (setup for
  the admin: [docs/connectwise-setup.md](docs/connectwise-setup.md)). Optional barcode of the ticket number, batch
  printing, reprint from history, your shop logo (Settings → Tag logo, kept per PC). Import your own DYMO Connect
  `.dymo` template (Layout → Import .dymo…), or click the preview and type anything for a **blank tag**.
- **Shipping labels** on the LabelWriter **5XL** (4″ × 6″). Paste a screenshot, drop the carrier's PDF, or just
  download it — LabelDesk finds the label on the page, turns it upright, fits it, and checks the barcode scans before it
  prints. Adjust with ↺ ↻ 180° or by dragging a box.
- **The preview is exactly what prints** — it's drawn at the printers' own 300 dpi.
- **Sets the printers up by itself:** finds the DYMO printers on the network, follows them when their address changes,
  and reads the loaded roll — which labels, how many are left — so it never prints on the wrong one.
- **Follows every job** until the printer has finished, and explains problems in plain English (out of labels, paused,
  printer not answering) with a Resume / Print again button.
- **Updates itself** from this repo; ideas and changes from the shop go to the owner for approval (see below).

## Install

You need the two DYMO printers on the shop network and, on Windows and Mac, DYMO's own software installed once (LabelDesk
prints through DYMO's driver). Pick your computer:

### Windows 11
1. Install **[DYMO Connect for Desktop](https://www.dymo.com/support?cfid=online-support-sw-downloads)** and add both
   printers in it. Can't find them (often on Wi-Fi)? See [SETUP.md section 3](SETUP.md#3-printers-that-cant-be-found-wi-fi-windows).
2. Download **`LabelDesk-<version>.msi`** from the **[latest release](https://github.com/cpkrepo/LabelDesk_Public/releases/latest)**
   and run it. No admin rights needed.
3. Start menu → **LabelDesk**. It also starts in the background when you log in.

### macOS (14 Sonoma or newer)
1. Install **[DYMO Connect for Mac](https://www.dymo.com/support?cfid=online-support-sw-downloads)** (it installs the
   driver for the 550 Turbo and 5XL). You don't need to add the printers in it.
2. Download **`LabelDesk-<version>.pkg`** from the **[latest release](https://github.com/cpkrepo/LabelDesk_Public/releases/latest)**
   and open it — the first time **right-click → Open** (it isn't signed by Apple; or System Settings → Privacy &
   Security → Open Anyway). It installs LabelDesk for you and finds the printers by itself. If it asks for Apple's
   developer tools, click Install in that window and open the package again when it's done.

   Or, in **Terminal**:
   ```bash
   xcode-select --install 2>/dev/null; git clone https://github.com/cpkrepo/LabelDesk_Public.git ~/LabelDesk_Public && cd ~/LabelDesk_Public && tools/install-all.sh
   ```
   (the Terminal way, step by step:) the first command installs Apple's developer tools (git + Python) if they're missing — click **Install** in the
   window that pops up, then paste the line again. `install-all.sh` finds both printers on the network (or asks for
   their IP addresses), asks for your Mac password once to add them, installs the app and runs a health check.
3. Open **LabelDesk** from Launchpad or Spotlight. It starts by itself when you log in.

### Fedora Linux
Paste in a terminal:
```bash
sudo dnf install -y git && git clone https://github.com/cpkrepo/LabelDesk_Public.git ~/LabelDesk_Public && cd ~/LabelDesk_Public && tools/install-all.sh
```
This builds DYMO's official 550-series driver, adds the two printers (found by name, or give their IPs:
`tools/add-printers.sh <550-Turbo-IP> <5XL-IP>`), installs the app and runs a health check. Then open **LabelDesk**
from the app menu.

### After installing (every computer)
- **Settings → Tag labels** must match the roll in the 550 Turbo (the shop's is **30252**).
- **Settings → Tag logo** → Choose logo… if you want the shop logo on tags.
- Give both printers a DHCP reservation in the router so their addresses don't change.

The full guide for technicians (printers that can't be found, GitHub access, publishing installers) is
**[SETUP.md](SETUP.md)**.

## Version history
**[CHANGELOG.md](CHANGELOG.md)** lists what's new in every version (newest first); each
[release](https://github.com/cpkrepo/LabelDesk_Public/releases) shows its own notes.

## Updates
After each print LabelDesk asks GitHub for the newest version number (one small file; nothing about your labels is
sent) and shows a notice when there's a newer one:
- **Windows:** **Install update** — downloads the installer from the release, checks its SHA-256, installs, restarts.
- **Mac and Fedora:** **Update now** — or run `tools/update.sh` in `~/LabelDesk_Public` if this computer has changes of
  its own (they're sent to the owner as a pull request, see below).

Want an older version on this PC? **Settings → Version** (below). Turn the check off with `"update_check": false` in the config file: Windows `%APPDATA%\LabelDesk\config.json`,
Mac `~/Library/Application Support/LabelDesk/config.json`, Fedora `~/.config/labeldesk/config.json`.

## Ideas and changes
LabelDesk is maintained by its owner, and every change is approved before anyone gets it:
- **Ask for a feature or report a problem:** [Issues → New issue](https://github.com/cpkrepo/LabelDesk_Public/issues/new/choose)
  (Feature request · Something's wrong · Please roll back). Never include customer names or real labels — this repo is public.
- **Propose a change yourself (with Claude Code):** open Claude Code in `~/LabelDesk_Public`, ask for the change. It
  follows `CLAUDE.md` and the skills in `.claude/skills/`, tests it, and `tools/update.sh` sends it as a **pull request**.
  The owner reviews it; only after it's merged and published does it reach the other PCs. Access and signing in:
  [SETUP.md section 5](SETUP.md#5-before-your-first-change-github-access).
- **A version turned out worse?** **Settings → Version** lists every version with what changed; pick one and press
  **Use this version** — LabelDesk switches by itself and stays there until **Back to the newest version**. The owner
  can tick **for every PC** to put an older version back for everyone. GitHub keeps every version.

## If something doesn't print
Run `tools/doctor.sh` in `~/LabelDesk_Public` (Mac and Fedora): it checks the driver, printers and app and says what's
wrong; `--fix` repairs the safe things. On Windows: LabelDesk → Settings → **DYMO printers by IP** → Check. More in
[.claude/skills/labeldesk-printer-setup/SKILL.md](.claude/skills/labeldesk-printer-setup/SKILL.md).

## Uninstall
- **Windows:** Settings → Apps → LabelDesk → Uninstall.
- **Mac / Fedora:** `tools/install-app.sh --remove` in `~/LabelDesk_Public`, then delete that folder. The printers stay
  for other apps (remove them in System Settings → Printers or `lpadmin -x Dymo-550-Turbo`).

## Development
Standard-library Python and plain JavaScript — no build step, no third-party packages. Tests:
`python3 -m unittest discover -s tests` · `node --test tests/*.mjs` · `tests/render_check.sh` · `tests/browser_check.sh`.
Every push runs the unit tests and a real print through DYMO's Mac driver on a Mac (Actions → macOS); every version
tag builds the Windows installer. Code map: [docs/dev/layout.md](docs/dev/layout.md).

## License
MIT (see [LICENSE](LICENSE)). No shop logo is included; each PC sets its own in Settings.
