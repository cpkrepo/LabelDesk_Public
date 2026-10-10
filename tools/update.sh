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
#  3. This PC's changes, tested (failing tests → nothing leaves this PC):
#     · on a TECHNICIAN's PC they go to GitHub as a PULL REQUEST (branch change/<pc>-<date>) for the owner to review —
#       nothing reaches main or the other PCs until the owner merges and publishes it;
#     · on the OWNER's PC ("publisher": GitHub admin, or git config labeldesk.publisher true) they are published: the
#       version goes up one (or stays if the change raised it), CHANGELOG.md gets its notes, main + tag v<version> are
#       pushed. The owner's update.sh also publishes pull requests merged on GitHub since the last version.
#  4. The app is restarted on the new code (tools/install-app.sh) if it's installed on this PC.
set -euo pipefail
cd "$(dirname "$0")/.."
REMOTE=${LABELDESK_REMOTE:-origin}
BRANCH=${LABELDESK_BRANCH:-main}
SRC='(\.(py|js|mjs|css|html|md|sh|ps1|pyw|te|wxs|svg|txt)|^templates/[^/]+\.json)$'   # + the shop's designer templates

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
    notes=$(git log --no-merges --format='- %s' "$2..HEAD" | grep -vE '^- (LabelDesk [0-9.]+(: changelog)?$|Local changes on |Merge )' || true)
    [ -n "$notes" ] || notes="- Small fixes."
  fi
  HEAD_LINE="## $1 — $(date +%Y-%m-%d)" NOTES="$notes" awk '        # (ENVIRON: BSD awk rejects newlines in -v)
    /^## Unreleased/ { print; print ""; print ENVIRON["HEAD_LINE"]; print ENVIRON["NOTES"]; skip=1; next }
    skip && /^## / { skip=0; print "" }
    !skip { print }' CHANGELOG.md > "$tmp" && mv "$tmp" CHANGELOG.md
  git add CHANGELOG.md; git commit --quiet -m "LabelDesk $1: changelog"
}
slug() { git remote get-url "$REMOTE" 2>/dev/null | sed -E 's#^.*github\.com[:/]##; s#\.git$##'; }
publisher() { # may this PC publish versions? Only the repo's owner (admin). Everyone else sends pull requests.
  case "${LABELDESK_ROLE:-}" in publisher) return 0;; contributor) return 1;; esac
  [ "$(git config --get labeldesk.publisher || true)" = true ] && return 0
  command -v gh >/dev/null 2>&1 && [ "$(gh api "repos/$(slug)" --jq .permissions.admin 2>/dev/null)" = true ]
}
run_tests() {
  echo "→ running the unit tests…"
  local log=${TMPDIR:-/tmp}/labeldesk-update-tests.log
  if ! python3 -m unittest discover -s tests -q >"$log" 2>&1; then
    tail -20 "$log"; die "tests failed — nothing left this PC. Full log: $log" 3
  fi
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

# ---- 2. this PC's commits on top of GitHub's newest (commits GitHub already has — a merged pull request — drop out)
if [ "$ahead" -gt 0 ] && [ "$behind" -gt 0 ]; then
  start=$(git rev-parse HEAD)
  if ! git rebase --quiet "$up" >/dev/null 2>&1; then
    git rebase --abort 2>/dev/null || true
    git reset --quiet --hard "$start"
    die "this PC's changes and GitHub's changes touch the same lines — nothing was changed or sent.
  Your work is safe in local commits ($ahead). Open Claude Code in $(pwd) and ask it to
  \"merge my unsent LabelDesk changes with GitHub's main, then run tools/update.sh\"." 2
  fi
  ahead=$(git rev-list --count "$up..HEAD")
elif [ "$ahead" -eq 0 ] && [ "$behind" -gt 0 ]; then
  git merge --quiet --ff-only "$up"
fi
[ "$ahead" -gt 0 ] || git config --unset labeldesk.proposal 2>/dev/null || true   # nothing of ours left out there
python3 - <<'PY' 2>/dev/null || true                     # updating = following updates again (Settings → Version hold off)
import json, os, sys
f = os.path.expanduser("~/Library/Application Support/LabelDesk/config.json" if sys.platform == "darwin" else "~/.config/labeldesk/config.json")
c = json.load(open(f))
if c.pop("hold_version", None) is not None:
    json.dump(c, open(f + ".tmp", "w"), indent=2); os.replace(f + ".tmp", f)
PY

# ---- 3a. owner: publish (this PC's commits, or pull requests merged on GitHub since the last version)
last_tag=$(git describe --tags --abbrev=0 --match 'v[0-9]*' HEAD 2>/dev/null || true)
if publisher; then
  if [ "$ahead" -eq 0 ] && { [ -z "$last_tag" ] || [ "$(git rev-parse "$last_tag^{commit}")" = "$(git rev-parse HEAD)" ]; }; then
    echo "✓ already up to date ($(ver))"
  else
    local_ver=$(ver)
    if newer "$local_ver" "$remote_ver"; then new_ver=$local_ver                   # the change already set a version
    elif [ -n "$last_tag" ] && ! git rev-parse -q --verify "refs/tags/v$remote_ver" >/dev/null; then
      new_ver=$remote_ver                                                       # raised in a merged pull request
    else IFS=. read -r a b c <<<"$remote_ver"; new_ver="$a.$b.$((${c:-0} + 1))"; fi
    if [ "$new_ver" != "$local_ver" ]; then
      echo "$new_ver" > VERSION; git add VERSION; git commit --quiet -m "LabelDesk $new_ver"
    fi
    changelog "$new_ver" "${last_tag:-$up}"
    run_tests
    git tag -f "v$new_ver" >/dev/null
    if ! git push --quiet "$REMOTE" "HEAD:$BRANCH" "refs/tags/v$new_ver"; then
      git tag -d "v$new_ver" >/dev/null
      die "GitHub refused the push (someone pushed meanwhile: just run this again). Your changes are kept here." 4
    fi
    echo "✓ published LabelDesk $new_ver"
  fi

# ---- 3b. technician: send this PC's changes as a pull request for the owner to review
elif [ "$ahead" -gt 0 ]; then
  run_tests
  host=$(hostname -s 2>/dev/null || hostname); pc=$(echo "$host" | tr 'A-Z' 'a-z' | tr -c 'a-z0-9-\n' '-')
  branch=$(git config --get labeldesk.proposal || echo "change/$pc-$(date +%Y%m%d-%H%M)")
  if ! git push --quiet --force-with-lease "$REMOTE" "HEAD:refs/heads/$branch"; then
    die "GitHub refused the push — this PC isn't signed in to GitHub, or you haven't accepted the invite to the repo
  (SETUP.md section 5). Your changes are kept here as local commits." 4
  fi
  git config labeldesk.proposal "$branch"
  title=$(git log --reverse --no-merges --format=%s "$up..HEAD" | grep -vE '^(Local changes on |LabelDesk [0-9.]+$)' | head -1 || true)
  title=${title:-Changes from $host}
  notes=$(awk '/^## Unreleased/{f=1;next} /^## /{f=0} f' CHANGELOG.md 2>/dev/null | grep '[^[:space:]]' || true)
  body="$(printf '**What changes for the people using LabelDesk:**\n%s\n\n**Commits:**\n%s\n\nUnit tests passed on %s (%s). Sent by tools/update.sh — nothing reaches main or the other PCs until the owner merges and publishes it.' \
    "${notes:-(no CHANGELOG notes)}" "$(git log --reverse --no-merges --format='- %s' "$up..HEAD")" "$host" "$(uname -s)")"
  url=""
  if command -v gh >/dev/null 2>&1; then
    url=$(gh pr view "$branch" --repo "$(slug)" --json url,state --jq 'select(.state == "OPEN") | .url' 2>/dev/null || true)
    if [ -n "$url" ]; then echo "✓ updated your pull request: $url"
    elif url=$(gh pr create --repo "$(slug)" --base "$BRANCH" --head "$branch" --title "$title" --body "$body" 2>/dev/null); then
      echo "✓ sent to the owner as a pull request: $url"
    else url=""; fi
  fi
  [ -n "$url" ] || echo "✓ sent as branch $branch — open the pull request: https://github.com/$(slug)/compare/$BRANCH...$branch"
  echo "  This PC runs your change now; the other PCs get it when the owner merges and publishes it."
else
  echo "✓ already up to date ($(ver))"
fi

# ---- 4. restart on the new code (only where the app is installed)
if [ -f ~/.config/systemd/user/labeldesk.service ] || [ -f ~/Library/LaunchAgents/com.labeldesk.app.plist ]; then tools/install-app.sh
else echo "(LabelDesk isn't installed as an app on this PC — skipping restart)"; fi
