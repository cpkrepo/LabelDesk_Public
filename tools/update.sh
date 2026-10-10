#!/usr/bin/env bash
# Update this LabelDesk checkout from GitHub WITHOUT losing anything changed on this PC.
#
#   tools/update.sh            update (what the "new version" notice tells you to run)
#   tools/update.sh --check    only report: local changes, unpushed commits, newer version on GitHub
#
#  1. Local edits are committed first: changes to files already in the repo, plus NEW source files
#     (.py .js .mjs .css .html .md .sh .ps1 .pyw .te .wxs .svg .txt). Anything else new (PDFs, images, .dymo,
#     databases, config) is NOT committed and is listed instead: it may be customer data and the repo is public.
#  2. Local commits are replayed on top of GitHub's newest version (git rebase).
#     A conflict stops everything and puts the checkout back exactly as it was (your commits are kept).
#  3. If this PC had changes: the version goes up one (0.6.0 → 0.6.1, or stays if the changes already raised it),
#     the unit tests must pass, then it is pushed to GitHub with a tag (v0.6.1). Failing tests → nothing is pushed.
#  4. The app is restarted on the new code (tools/install-app.sh) if it's installed on this PC.
set -euo pipefail
cd "$(dirname "$0")/.."
REMOTE=${LABELDESK_REMOTE:-origin}
BRANCH=${LABELDESK_BRANCH:-main}
SRC='\.(py|js|mjs|css|html|md|sh|ps1|pyw|te|wxs|svg|txt)$'

die() { echo "✗ $1" >&2; exit "${2:-1}"; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "this folder isn't a git checkout — install from GitHub (README → Install) to get updates"
[ -z "$(git rev-parse -q --verify REBASE_HEAD 2>/dev/null || true)" ] || die "a rebase is already in progress here — finish or abort it first (git rebase --abort)"

ver() { tr -d '[:space:]' < VERSION 2>/dev/null || echo 0.0.0; }
changelog() { # changelog VERSION UPSTREAM: "## Unreleased" notes become "## VERSION — date" (none written: this PC's
  # commit messages instead), so every version on GitHub says what changed (README → CHANGELOG.md, release notes)
  [ -f CHANGELOG.md ] && grep -q '^## Unreleased' CHANGELOG.md || return 0
  ! grep -q "^## $1 " CHANGELOG.md || return 0
  local notes tmp; tmp=$(mktemp)
  notes=$(awk '/^## Unreleased/{f=1;next} /^## /{f=0} f' CHANGELOG.md | grep '[^[:space:]]' || true)
  if [ -z "$notes" ]; then
    notes=$(git log --no-merges --format='- %s' "$2..HEAD" | grep -vE '^- (LabelDesk [0-9.]+$|Local changes on )' || true)
    [ -n "$notes" ] || notes="- Small fixes."
  fi
  HEAD_LINE="## $1 — $(date +%Y-%m-%d)" NOTES="$notes" awk '        # (ENVIRON: BSD awk rejects newlines in -v)
    /^## Unreleased/ { print; print ""; print ENVIRON["HEAD_LINE"]; print ENVIRON["NOTES"]; skip=1; next }
    skip && /^## / { skip=0; print "" }
    !skip { print }' CHANGELOG.md > "$tmp" && mv "$tmp" CHANGELOG.md
  git add CHANGELOG.md; git commit --quiet -m "LabelDesk $1: changelog"
}
newer() { # newer A B → true if version A > version B
  [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -t. -k1,1n -k2,2n -k3,3n | tail -1)" = "$1" ]; }

echo "→ asking GitHub for the newest version ($REMOTE/$BRANCH)…"
git fetch --quiet --tags "$REMOTE" "$BRANCH" || die "couldn't reach GitHub (git fetch failed)"
up="$REMOTE/$BRANCH"
remote_ver=$(git show "$up:VERSION" 2>/dev/null | tr -d '[:space:]' || echo 0.0.0)

# ---- 1. what's changed on this PC
new_src=(); new_other=()                    # (no mapfile: macOS ships bash 3.2)
while IFS= read -r f; do [ -n "$f" ] && new_src+=("$f"); done < <(git ls-files --others --exclude-standard | grep -E "$SRC" || true)
while IFS= read -r f; do [ -n "$f" ] && new_other+=("$f"); done < <(git ls-files --others --exclude-standard | grep -vE "$SRC" || true)
dirty=$(git status --porcelain --untracked-files=no)
ahead=$(git rev-list --count "$up..HEAD" 2>/dev/null || echo 0)
behind=$(git rev-list --count "HEAD..$up" 2>/dev/null || echo 0)

if [ "${1:-}" = "--check" ]; then
  echo "this PC: $(ver) · GitHub: $remote_ver · edited files: $(echo -n "$dirty" | grep -c . || true) · new source files: ${#new_src[@]}" \
       "· unpushed commits: $ahead · GitHub commits not here yet: $behind"
  [ ${#new_other[@]} -eq 0 ] || printf '  not committed (not source): %s\n' "${new_other[@]}"
  exit 0
fi

git config user.name >/dev/null || die "git doesn't know who you are yet: git config --global user.name \"Your Name\"; git config --global user.email \"you@example.com\""
if [ -n "$dirty" ] || [ ${#new_src[@]} -gt 0 ]; then
  git add -u
  [ ${#new_src[@]} -eq 0 ] || git add -- "${new_src[@]}"
  git commit --quiet -m "Local changes on $(hostname -s 2>/dev/null || hostname) before update"
  echo "✓ committed this PC's changes"
  ahead=$(git rev-list --count "$up..HEAD")
fi
if [ ${#new_other[@]} -gt 0 ]; then
  echo "! these new files were NOT committed (may be work data; the repo is public). Add them yourself if they belong:"
  printf '    %s\n' "${new_other[@]}"
fi

# ---- 2. nothing of ours to merge: just move to GitHub's version
if [ "$ahead" -eq 0 ]; then
  if [ "$behind" -eq 0 ]; then echo "✓ already up to date ($(ver))"
  else git merge --quiet --ff-only "$up"; echo "✓ updated to $(ver)"; fi
else
  # ---- our commits on top of GitHub's newest
  start=$(git rev-parse HEAD)
  if [ "$behind" -gt 0 ] && ! git rebase --quiet "$up" >/dev/null 2>&1; then
    git rebase --abort 2>/dev/null || true
    git reset --quiet --hard "$start"
    die "this PC's changes and GitHub's changes touch the same lines — nothing was changed or pushed.
  Your work is safe in local commits ($ahead). Open Claude Code in $(pwd) and ask it to
  \"merge my unpushed LabelDesk changes with GitHub's main, then run tools/update.sh\"." 2
  fi
  # ---- 3. new version, tests, push
  local_ver=$(ver)
  if newer "$local_ver" "$remote_ver"; then new_ver=$local_ver                     # the change already set a version
  else IFS=. read -r a b c <<<"$remote_ver"; new_ver="$a.$b.$((${c:-0} + 1))"; fi
  if [ "$new_ver" != "$local_ver" ]; then
    echo "$new_ver" > VERSION; git add VERSION; git commit --quiet -m "LabelDesk $new_ver"
  fi
  changelog "$new_ver" "$up"
  echo "→ running the unit tests before pushing…"
  if ! python3 -m unittest discover -s tests -q >/tmp/labeldesk-update-tests.log 2>&1; then
    tail -20 /tmp/labeldesk-update-tests.log
    die "tests failed — nothing was pushed. Full log: /tmp/labeldesk-update-tests.log" 3
  fi
  git tag -f "v$new_ver" >/dev/null
  if ! git push --quiet "$REMOTE" "HEAD:$BRANCH" "refs/tags/v$new_ver"; then
    die "GitHub refused the push (no write access, or someone pushed meanwhile: just run this again).
  Your changes are kept here as local commits." 4
  fi
  echo "✓ pushed LabelDesk $new_ver to GitHub"
fi

# ---- 4. restart on the new code (only where the app is installed)
if [ -f ~/.config/systemd/user/labeldesk.service ] || [ -f ~/Library/LaunchAgents/com.labeldesk.app.plist ]; then tools/install-app.sh
else echo "(LabelDesk isn't installed as an app on this PC — skipping restart)"; fi
