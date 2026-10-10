#!/usr/bin/env bash
# Undo a bad version: publish an OLDER version's code again, as the NEXT version number, so every PC moves to it
# the normal way (Fedora/Mac: Update now / tools/update.sh; Windows: Install update — the Action builds its MSI).
#
#   tools/rollback.sh                       list the recent versions (newest first) with what changed
#   tools/rollback.sh 0.7.0 "why"           GitHub's main becomes 0.7.0's code, published as e.g. 0.7.3 + tag v0.7.3
#
# Nothing is deleted: the bad version stays in the history and can be brought back the same way (rollback to it).
# Kept from the current version so they're never lost: this script, its test, the rollback skill and CHANGELOG.md
# (which gets a "Rolled back" entry).
# Needs: no unpushed work on this PC (run tools/update.sh first), and the unit tests of the old code must pass.
set -euo pipefail
cd "$(dirname "$0")/.."
REMOTE=${LABELDESK_REMOTE:-origin}
BRANCH=${LABELDESK_BRANCH:-main}
KEEP="tools/rollback.sh tests/test_rollback.py .claude/skills/labeldesk-rollback CHANGELOG.md .gitattributes"

die() { echo "✗ $1" >&2; exit "${2:-1}"; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "this folder isn't a git checkout"
git fetch --quiet --tags "$REMOTE" "$BRANCH" || die "couldn't reach GitHub (git fetch failed)"
up="$REMOTE/$BRANCH"
remote_ver=$(git show "$up:VERSION" | tr -d '[:space:]')

if [ $# -eq 0 ]; then
  echo "GitHub has $remote_ver. Recent versions (tools/rollback.sh <version> \"why\" to go back to one):"
  git for-each-ref --sort=-creatordate --count=15 --format='%(refname:short)' 'refs/tags/v*' | while read -r t; do
    printf '  %-8s %s  %s\n' "${t#v}" "$(git log -1 --format=%cs "$t")" "$(git log -1 --format=%s "$t" | cut -c1-90)"
  done
  exit 0
fi

old=${1#v}; why=${2:-}
git rev-parse -q --verify "refs/tags/v$old" >/dev/null || die "there's no version $old (tools/rollback.sh lists them)"
[ "$old" != "$remote_ver" ] || die "$old is already the newest version"
[ -z "$(git status --porcelain --untracked-files=no)" ] || die "this PC has uncommitted changes — run tools/update.sh first (or git stash)"
[ "$(git rev-list --count "$up..HEAD")" = 0 ] || die "this PC has commits that aren't on GitHub — run tools/update.sh first"
git config user.name >/dev/null || die "git doesn't know who you are yet: git config --global user.name \"Your Name\""

git merge --quiet --ff-only "$up"
start=$(git rev-parse HEAD)
IFS=. read -r a b c <<<"$remote_ver"; new="$a.$b.$((${c:-0} + 1))"
git read-tree -u --reset "v$old"                                  # the old version's files exactly (newer files go away)
for k in $KEEP; do git checkout "$start" -- "$k" 2>/dev/null || true; done   # (already staged when it exists)
echo "$new" > VERSION
git add VERSION
if [ -f CHANGELOG.md ] && grep -q '^## Unreleased' CHANGELOG.md; then                # the history says what happened
  tmp=$(mktemp)
  HEAD_LINE="## $new — $(date +%Y-%m-%d)" NOTES="- **Rolled back** to the code of $old${why:+ — $why}. (Undo: \`tools/rollback.sh $remote_ver\`)" \
    awk '/^## Unreleased/ { print; print ""; print ENVIRON["HEAD_LINE"]; print ENVIRON["NOTES"]; next } { print }' CHANGELOG.md > "$tmp"
  mv "$tmp" CHANGELOG.md; git add CHANGELOG.md
fi
git commit --quiet -m "Roll back to $old (published as $new)${why:+: $why}" \
  -m "Code of v$old, except $KEEP (kept from $remote_ver). Undo: tools/rollback.sh $remote_ver"

echo "→ running the unit tests of $old before publishing…"
log=${TMPDIR:-/tmp}/labeldesk-rollback-tests.log
if ! python3 -m unittest discover -s tests -q >"$log" 2>&1; then
  tail -20 "$log"; git reset --quiet --hard "$start"
  die "tests failed — nothing was published, this PC is back on $remote_ver. Log: $log" 3
fi
git tag "v$new"
if ! git push --quiet "$REMOTE" "HEAD:$BRANCH" "refs/tags/v$new"; then
  git tag -d "v$new" >/dev/null; git reset --quiet --hard "$start"
  die "GitHub refused the push (no write access, or someone pushed meanwhile: run this again)" 4
fi
echo "✓ GitHub's newest version is now $new = the code of $old. PCs get it with their next update."

if [ -f ~/.config/systemd/user/labeldesk.service ] || [ -f ~/Library/LaunchAgents/com.labeldesk.app.plist ]; then
  tools/install-app.sh
fi
