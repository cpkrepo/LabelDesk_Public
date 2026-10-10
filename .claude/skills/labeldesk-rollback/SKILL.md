---
name: labeldesk-rollback
description: Roll LabelDesk back when a new version is bad: publish an older version's code as the next version so every PC (Fedora, Mac, Windows) moves to it. Use for "undo", "go back", "revert".
---

# Rolling LabelDesk back

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
