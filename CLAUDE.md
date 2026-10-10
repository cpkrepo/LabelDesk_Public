# LabelDesk — brief (loaded every turn: keep it tiny; detail in docs/dev/)
DYMO label printing for the shop on Fedora, macOS (both: git clone + CUPS, http://127.0.0.1:8792) and Windows 11 (per-user
.msi), replacing DYMO Connect. macOS: tools/mac/ (tools/*.sh hand off there), docs/dev/mac.md.
Several technicians run it and change it with Claude; this checkout is a clone of the PUBLIC repo
github.com/cpkrepo/LabelDesk_Public. Read only what the task needs: docs/dev/layout.md (code map, tests) ·
docs/dev/facts.md (driver, SELinux, CUPS tiling, 550 handshake, label detection) · docs/dev/windows.md (build, test VM,
updates) · docs/dev/connectwise.md · docs/dev/open-items.md · docs/dev/printers.md · docs/dev/working.md.
Skills in .claude/skills: labeldesk-printer-setup · labeldesk-testing · dymo-template-import · labeldesk-rollback (descriptions ≤ 200 chars:
Claude.ai rejects longer; tools/package-skills.sh checks). People-facing setup: SETUP.md (keep it true when you change
install/update/printer steps). License MIT. Version tags (v*) trigger .github/workflows/windows-installer.yml → MSI + .sha256 on the release, which
the Windows app's "Install update" uses.

## Printers (facts — don't reinterpret)
- 550 Turbo (Ethernet): inventory tags on **30252 Address, 1-1/8"×3-1/2"** (the shop's roll, measured 2026-10-08) — page
  `w79h252`, canvas 298×962. 30321 Large Address (1.4"×3.5", `w102h252`, 391×960) is selectable in Settings → Tag labels
  (config `tag_label`). Queue `Dymo-550-Turbo`. drawTag scales its sizes by label height (k = height/391).
  Tag = company/customer · `Received: MM/DD/YYYY` · `Ticket#: …`, optional Code 128, shop logo bottom-right (built-in layout).
  Blank tag: click the preview, type (fields `{free: text}`). The logo is PER PC (config folder, Settings → Tag logo, /api/logo)
  and must never be added to the repo.
- 5XL (Ethernet): shipping 4"×6" (1744907) — queue `Dymo-5XL`. UPS/FedEx label pasted/dropped/opened → trimmed, turned, fitted.

## Invariants
- The browser draws the label; the server only prints the PNG. **The preview is the print.**
- Never disable SELinux (use tools/selinux/dymo_cups.te). Genuine DYMO rolls only (NFC) — not a bug.
- ConnectWise: optional, read-only, invisible and no ConnectWise calls unless ON; never write to it; never ask for keys in chat.
- Customer names are work data: they stay on the PC. **The repo is public**: never commit real labels, carrier PDFs,
  screenshots, .dymo files from work, databases, config.json or keys (.gitignore blocks the usual ones — don't force-add).
- Outbound calls: ConnectWise (when ON) and, after each print, a GET of GitHub's VERSION file (nothing else, no label data).

## Shipping a change (every technician, every change — no need to ask)
1. Make the change; test at the level it needs (labeldesk-testing skill; app.js changes need the render check) and say
   which level you reached.
2. Version: the version lives only in `./VERSION`. Raise it yourself for a feature (0.6.x → 0.7.0); otherwise leave it —
   update.sh adds one to the last number.
3. Commit with a real message, then run `tools/update.sh`: it commits leftovers, rebases this PC's commits onto GitHub's
   newest main, bumps VERSION if needed, runs the unit tests, pushes main + tag `v<version>`, restarts the app.
4. If update.sh stops on a **conflict** (exit 2): nothing was pushed and the checkout is back as it was. Merge it here —
   `git fetch && git rebase origin/main`, resolve keeping BOTH sides' intent, run the tests (and render check if app.js
   changed), `git rebase --continue`, then `tools/update.sh` again. Tests failing (exit 3): fix, don't skip.
   Push refused (exit 4): this technician has no write access — say so; keep the commits.
5. When asked to "update LabelDesk": run `tools/update.sh --check` first and report what's local/unpushed, then `tools/update.sh`.
6. A version is bad ("roll back", "undo", "go back to 0.7.0"): labeldesk-rollback skill (`tools/rollback.sh`). Never
   force-push or delete tags — GitHub refuses it (rulesets), and rollback = an old version republished as a new number.
- Tick or add items in docs/dev/open-items.md when a fact changes.
