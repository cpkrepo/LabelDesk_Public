# LabelDesk setup guide for technicians

Everything a technician needs, in order. The short version is in README.md.

1. [Install LabelDesk on Fedora](#1-install-labeldesk-on-fedora)
2. [Install LabelDesk on Windows](#2-install-labeldesk-on-windows)
   · [on a Mac](#install-labeldesk-on-a-mac)
3. [Printers that can't be found (Wi-Fi, Windows)](#3-printers-that-cant-be-found-wi-fi-windows)
4. [Claude: Claude Code and the skills](#4-claude-claude-code-and-the-skills)
5. [Before your first change: GitHub access](#5-before-your-first-change-github-access)
6. [Suggesting changes (pull requests and feature requests)](#6-suggesting-changes-pull-requests-and-feature-requests)
7. [Publishing a Windows installer](#7-publishing-a-windows-installer)
8. [Updates, turning the check off, uninstalling](#8-updates-turning-the-check-off-uninstalling)
9. [Labels remaining (finding out first)](#9-labels-remaining-finding-out-first)

**The repository is public.** Never commit real shipping labels, carrier PDFs, screenshots, `.dymo` files from work,
the history database, `config.json` or ConnectWise keys. `.gitignore` and `tools/update.sh` block the usual ones; don't
force-add around them.

---

## 1. Install LabelDesk on Fedora

```bash
sudo dnf install -y git
git clone https://github.com/cpkrepo/LabelDesk_Public.git ~/LabelDesk_Public
cd ~/LabelDesk_Public && tools/install-all.sh
```
`install-all.sh` builds DYMO's 550-series driver, adds the two printer queues, installs the app and runs a health check.
It asks for your password (sudo) for the driver and printers.

**Printer IPs.** `add-printers.sh` finds the printers by name on the network. If it can't, it asks for their IP
addresses: read them from the printer's network status or the router's DHCP list, then run
`tools/add-printers.sh <550-Turbo-IP> <5XL-IP>`. Give both printers a DHCP reservation so the IPs don't change.

**Already running LabelDesk from an unzipped folder?** Clone as above, then run only `tools/install-app.sh` from the
clone (the driver and printers are already set up). History and settings are kept; they live in your home folder.
Delete the old folder afterwards.

Open **LabelDesk** from the app menu (or http://127.0.0.1:8792). Then, once per PC:
- **Tag labels:** Settings → **Tag labels** must match the roll in the 550 Turbo. The shop's roll is **30252**
  (1⅛″ × 3½″, the default); choose 30321 only for 1.4″ labels. The wrong one prints text off the label's edge.
- **Shop logo:** Settings → **Tag logo** → Choose logo… (PNG or JPEG). It's stored on this PC only and never goes into
  the repo; without one, tags print without a logo.
- Print one tag; if it comes out upside down, tick "Rotate 180°" under the preview. If the top line is cut off, use the
  ↑/↓ text position buttons.

**Blank tag:** click the tag preview and type (several lines are fine); Ctrl+Enter prints it, Esc goes back.

## 2. Install LabelDesk on Windows

1. Install **DYMO Connect** and add both printers in it (LabelDesk prints through DYMO's driver). If DYMO Connect can't
   find the printers, see section 3.
2. Download `LabelDesk-<version>.msi` from the repo's **Releases** page and run it. No admin rights needed.
3. Start menu → **LabelDesk**. It also starts in the background at login.
4. Settings → **Tag logo** → Choose logo… (once per PC).
5. Optional: Settings → **Add the Shipping Label printer** (asks for an administrator) so you can print a UPS/FedEx
   page from the browser straight into LabelDesk.

### Install LabelDesk on a Mac

macOS 14 (Sonoma) or newer, Intel or Apple silicon. LabelDesk prints through the driver that DYMO Connect for Mac
installs, and runs from a clone of this repo like on Fedora (same `tools/update.sh`, same Claude Code workflow).

1. Install **DYMO Connect for Mac** from DYMO's download page
   (https://www.dymo.com/support?cfid=online-support-sw-downloads). Adding the printers in it is optional.
2. **Easiest:** download `LabelDesk-<version>.pkg` from the repo's Releases page and open it (first time: right-click →
   Open — it isn't signed by Apple). It clones LabelDesk into `~/LabelDesk_Public`, installs the app and the printers set
   themselves up; if it asks for Apple's developer tools, install them and open the package again. Log:
   `/tmp/labeldesk-install.log`. **Or** in **Terminal**:
   ```bash
   xcode-select --install          # git + python3 from Apple; click Install, wait, skip if "already installed"
   git clone https://github.com/cpkrepo/LabelDesk_Public.git ~/LabelDesk_Public
   cd ~/LabelDesk_Public && tools/install-all.sh          # or: tools/install-all.sh <550-Turbo-IP> <5XL-IP>
   ```
   It checks the DYMO driver, adds the queues **Dymo-550-Turbo** and **Dymo-5XL** (asks for your Mac password),
   installs a LaunchAgent that runs LabelDesk at login plus **LabelDesk.app** in `~/Applications`, and runs
   `tools/doctor.sh`.
3. Open **LabelDesk** from Launchpad or Spotlight. Then Settings → **Tag labels** (30252) and **Tag logo**, as on Fedora.

Mac notes: settings, history and the logo live in `~/Library/Application Support/LabelDesk`, the log in
`~/Library/Logs/LabelDesk.log`, ConnectWise keys in the login Keychain ("LabelDesk ConnectWise"). There's no
"Shipping Label" print-dialog printer on the Mac: in a carrier's print dialog choose **PDF → Save as PDF** into
Downloads and LabelDesk opens it by itself. `brew install zbar` (optional) adds a second barcode check; without it the
browser checks barcodes, as on Windows.

## 3. Printers that can't be found (Wi-Fi, Windows)

The printers are on wired Ethernet. A Windows PC on Wi-Fi may not see them in DYMO Connect or "Add a printer". Find
out why before changing anything; the two scripts are in the repo's `windows/` folder and installed beside LabelDesk
in `%LOCALAPPDATA%\Programs\LabelDesk`.

**Easiest:** LabelDesk → Settings → **DYMO printers by IP**: type the IPs, click **Check** (read-only; the result shows
right there), then **Add 550 Turbo** / **Add 5XL** if the check says `tcp 9100: open` (Windows asks for an
administrator; a window shows the result). The same two scripts can also be run by hand:

**Check (read-only, no admin).** In PowerShell on the Windows PC:
```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\Programs\LabelDesk\printer-check.ps1" -PrinterIP 192.0.2.10,192.0.2.11
```
(use the printers' real IPs). It reports whether the PC is on Wi-Fi or wired, its subnet, whether Windows treats the
network as **Public** (that turns network discovery off), whether each printer answers on port 9100, which DYMO
drivers are installed, and which DYMO printers already exist.

**What the result means:**
- **Port 9100 open but the printer can't be found:** discovery doesn't reach this PC. Add it by IP (below).
- **No answer on 9100 and a different subnet:** the Wi-Fi network can't reach the printers' network (guest Wi-Fi,
  separate VLAN, or the access point isolating clients). That's a network fix; adding by IP won't print either.
- **No answer on the same subnet:** printer off or asleep, wrong IP, or client isolation. Try from a wired PC to tell
  them apart.
- **No DYMO drivers:** install DYMO Connect first.

**Add by IP (admin PowerShell; reversible).**
```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\Programs\LabelDesk\add-dymo-printer.ps1" -Model 550 -IP 192.0.2.10
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\Programs\LabelDesk\add-dymo-printer.ps1" -Model 5XL -IP 192.0.2.11
```
It refuses to change anything if port 9100 doesn't answer or the DYMO driver is missing. `-Remove` (with `-Model`)
takes the printer back out. If the printer's IP changes later, remove it and add it again.

## 4. Claude: Claude Code and the skills

LabelDesk ships three Claude skills in `.claude/skills/`: **labeldesk-printer-setup** (driver, queues, printing
problems, Windows printers), **labeldesk-testing** (how to test a change) and **dymo-template-import** (matching a
DYMO Connect template). `CLAUDE.md` tells Claude how the project works and how to ship changes.

**Claude Code (recommended for changing LabelDesk).** Needs a Claude plan that includes Claude Code.
```bash
curl -fsSL https://claude.ai/install.sh | bash        # Fedora and Mac; on Windows PowerShell: irm https://claude.ai/install.ps1 | iex
cd ~/LabelDesk_Public && claude                       # sign in the first time
```
Start it **inside the clone**: it then reads `CLAUDE.md` and loads the three skills by itself, nothing to install.
Type `/skills` to see them. Current install instructions: https://docs.claude.com/en/docs/claude-code/overview

**Claude.ai chat (optional, for questions and troubleshooting).** Chat can't run commands on your PC, but the skills
give it the printer and testing know-how.
1. In the clone: `tools/package-skills.sh` → `dist/skills/<skill>.zip`, one ZIP per skill.
2. Claude.ai → **Customize → Skills** → upload each ZIP and switch it on. Code execution must be enabled for skills.
3. On a Team or Enterprise plan, an admin can provision the skills for the whole organization instead.
Details: https://support.claude.com/en/articles/12512198-how-to-create-custom-skills

When a skill changes in the repo, Claude Code picks it up on the next start; Claude.ai needs the new ZIP uploaded.

## 5. Before your first change: GitHub access

1. **A GitHub account,** invited by the repo owner: repo **Settings → Collaborators → Add people**. Accept the email
   invite. Without it you can still install and update, but your changes can't be pushed.
   The very first publish (empty repo): the owner pushes `main`, then `git tag v$(cat VERSION) && git push origin --tags`
   so the Action builds the first Windows installer.
2. **Your name and a private email for commits.** Every commit shows this email publicly. On GitHub, Settings →
   Emails → tick "Keep my email addresses private" and copy the `…@users.noreply.github.com` address shown there:
   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "12345678+yourname@users.noreply.github.com"
   ```
3. **Sign this PC in to GitHub** so pushes work:
   ```bash
   sudo dnf install -y gh && gh auth login && gh auth setup-git          # Fedora
   brew install gh && gh auth login && gh auth setup-git                 # Mac (or the .pkg from cli.github.com)
   ```
   Choose GitHub.com, HTTPS, and log in with the browser.

## 6. Suggesting changes (pull requests and feature requests)

**Only the owner publishes new versions.** Nobody else's change reaches `main` or the other PCs until the owner has
reviewed and approved it — GitHub enforces this (owner-approved pull requests only; only the owner creates versions).

**Just an idea?** Repo → **Issues → New issue → Feature request** (or "Something's wrong", "Please roll back"), or ask
Claude Code to file it. No code needed. Never paste customer names, addresses or real labels: the repo is public.

**Want to make the change yourself?** Ask Claude Code (started in the clone) for it. It tests it, notes it in
`CHANGELOG.md`, commits it and runs `tools/update.sh`, which:
1. commits anything changed on this PC (source files only; it lists other new files instead of committing them),
2. puts your commits on top of the newest version on GitHub,
3. runs the unit tests,
4. pushes them to your own branch (`change/<this-pc>-<date>`) and opens a **pull request** for the owner,
5. restarts LabelDesk here on your change. The other PCs get it only when the owner merges and publishes it.

Running it again with more changes updates the same pull request. Once the owner has published it, `tools/update.sh`
(or **Update now**) brings this PC back in line with everyone else. If the owner declines it, ask Claude Code to
"put this PC back on GitHub's version" (`git fetch && git reset --hard origin/main`).

**If update.sh stops,** nothing was sent and your work is safe in local commits:

| Message | What to do |
|---|---|
| "touch the same lines" (conflict) | Ask Claude Code: "merge my unsent LabelDesk changes with GitHub's main, then run tools/update.sh". |
| "tests failed" | Ask Claude Code to fix the failing test (log: `/tmp/labeldesk-update-tests.log`). Don't skip tests. |
| "GitHub refused the push" | Not invited / not signed in (section 5). |
| "git doesn't know who you are" | Section 5, step 2. |
| "isn't a git checkout" | This copy came from a zip: reinstall from the clone (section 1). |

**For the owner:** review pull requests on GitHub (Files changed → Review → Approve → **Merge**; squash merging is off so
technicians' PCs recognise their own merged work). Then run `tools/update.sh` on your PC: it publishes everything merged
since the last version (version number, changelog, tests, tag → Windows installer). Your own changes publish directly.

**A new version is bad?** LabelDesk → **Settings → Version**: the list of every published version (from GitHub) with
what changed. Pick one → **Use this version** → OK. LabelDesk switches by itself (Windows: uninstalls this version and
installs the chosen one; Fedora/Mac: checks it out) and restarts; this PC then stays on it — no update notices — until
**Back to the newest version**. Your settings, logo and history are kept.

On the owner's PC the same screen has **For every PC**: it publishes the chosen version's code as the next version
number (`tools/rollback.sh`), so every PC goes back with its normal update — Windows included. The bad version isn't
erased; it can be brought back the same way. Technicians who think everyone should go back: **Please roll back** issue.

## 7. Publishing a Windows installer

**Automatic.** Every version tag that `tools/update.sh` pushes starts the GitHub Action "Windows installer"
(`.github/workflows/windows-installer.yml`): it runs the unit tests, builds `LabelDesk-<version>.msi` and attaches it
with its `.sha256` to that release. Windows PCs then offer **Install update** after their next print. Check progress in
the repo's **Actions** tab; a red run means no installer for that version (fix it, then "Run workflow" there).

**By hand** (if Actions is off): on a Fedora PC with a clone,
```bash
sudo dnf install -y msitools rsync librsvg2-tools ImageMagick gh
cd ~/LabelDesk_Public && git pull && tools/build-windows.sh
v=$(cat VERSION); gh release create "v$v" "dist/LabelDesk-$v.msi" "dist/LabelDesk-$v.msi.sha256" --verify-tag --title "LabelDesk $v" --notes "LabelDesk $v"
```
Upload the `.sha256` too: Install update refuses an installer without a matching checksum.

## 8. Updates, turning the check off, uninstalling

- **Update notice.** After every print LabelDesk fetches the newest version number from GitHub (one small file;
  nothing about your labels is sent).
  - **Fedora and Mac, no changes of your own:** **Update now**. LabelDesk updates and restarts itself (about a minute); the
    page reloads. If it doesn't, the notice shows the end of the log and the command to run.
  - **Fedora and Mac with your own changes:** the notice shows `tools/update.sh` to run in a Terminal, so your changes get merged
    and pushed (section 6).
  - **Windows:** **Install update** downloads the installer from the release, checks its SHA-256, installs it and
    restarts LabelDesk. Settings, history and the logo are kept.
- **Turn the check off:** add `"update_check": false` to `~/.config/labeldesk/config.json`
  (Mac: `~/Library/Application Support/LabelDesk/config.json`; Windows: `%APPDATA%\LabelDesk\config.json`) and restart LabelDesk.
- **Uninstall on a Mac:** `tools/install-app.sh --remove`, then delete `~/LabelDesk_Public` (history stays in
  `~/Library/Application Support/LabelDesk`). The printer queues and DYMO Connect stay.
- **Uninstall on Fedora:** `tools/install-app.sh --remove` (history stays in `~/.local/share/labeldesk`; delete that
  folder too to remove everything), then delete the clone. The printer queues and driver stay for other apps.
- **Uninstall on Windows:** Settings → Apps → LabelDesk → Uninstall.

## 9. Labels remaining (finding out first)

Whether the 550 reports how many labels are left on the roll isn't known yet. Before anyone builds that display, at
work with a real printer:
```bash
tools/dymo-status.py <printer-IP> --save before.json      # read-only status (the same request DYMO's driver makes)
# print 3 labels, then:
tools/dymo-status.py <printer-IP> --compare before.json   # which status bytes changed, and by how much
```
If one byte (or byte pair) dropped by exactly 3, that's the counter: note it in docs/dev/open-items.md.

LabelDesk is MIT licensed (see `LICENSE`). No shop logo is included in the repo.
