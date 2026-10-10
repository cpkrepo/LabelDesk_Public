---
name: labeldesk-rollback
description: Roll LabelDesk back when a new version is bad (owner only; others file a rollback request). Use for "undo", "go back", "revert", "roll back".
---

# Rolling LabelDesk back

**People do this themselves in the app: Settings → Version** (list from GitHub's releases → Use this version; this PC
only, held there; owner's PC: "For every PC"). Point users there first. The tools below are what it runs
(`tools/switch-version.sh <v>|newest [--everyone]` → `tools/rollback.sh`).

**Only the owner publishes versions, rollbacks included** (`tools/rollback.sh` checks: GitHub admin, or
`git config labeldesk.publisher true`; anyone else gets exit 5). On a technician's PC, don't try to work around it —
file the request instead and tell the user it went to the owner:
`gh issue create --repo cpkrepo/LabelDesk_Public --title "Please roll LabelDesk back to <version>" --label rollback --body "<what's wrong>"`
(or the "Please roll back" form under Issues → New issue).

On the owner's PC:

A version that "sucks" is undone by **publishing an older version's code again as the next version number**. PCs only
ever update forward, so this is what makes every Fedora/Mac PC (Update now / `tools/update.sh`) and every Windows PC
(Install update — the GitHub Action builds the MSI for the new tag) actually go back. Nothing is erased: the bad
version stays in the history and the rollback itself can be undone the same way.

1. `tools/rollback.sh` — lists recent versions (newest first) with date and commit message. Show the user the list and
   agree on the version to go back to (usually the one just before the bad one). Don't guess if it's unclear.
2. If this PC has unpushed work, `tools/rollback.sh` refuses: run `tools/update.sh` first (or ask the user).
3. `tools/rollback.sh <version> "<one line: what was wrong>"` — restores that version's files (keeps rollback.sh, its
   test and this skill), sets VERSION to GitHub's newest + 1, runs the old code's unit tests, pushes main + tag.
   Exit 3 = the old version's tests fail here (nothing pushed) — tell the user; pick another version.
   Exit 4 = push refused (no write access, or someone pushed meanwhile — run it again).
4. Tell the user which version is now live (e.g. "0.7.3 = the code of 0.7.0") and that PCs pick it up after their
   next print. Windows: check the repo's Actions tab turns green for the new tag.

To fix the bad version properly later: check out its commit, re-apply the good parts on top of current main and ship
with `tools/update.sh` as usual.

Never `git push --force`, delete tags or rewrite main: GitHub refuses it (rulesets "Keep main's history" and "Release
tags are permanent"), and it would break the PCs' updates.
