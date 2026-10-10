#!/usr/bin/env bash
# Put THIS PC on another published version of LabelDesk (Fedora / Mac; Windows does the same with the installer).
# Run by Settings → Version → "Use this version" (logged to update.log); works in a Terminal too:
#   tools/switch-version.sh 0.8.1      this PC runs 0.8.1 and stays there (no update notices) until…
#   tools/switch-version.sh newest     …it goes back to the newest version and follows updates again
#   tools/switch-version.sh 0.8.1 --everyone   OWNER only: publish 0.8.1's code as the next version for every PC
#                                              (tools/rollback.sh), then this PC updates to it
# Refuses when this PC has changes that aren't on GitHub (they'd be lost) — tools/update.sh sends them first.
set -euo pipefail
cd "$(dirname "$0")/.."
REMOTE=${LABELDESK_REMOTE:-origin}
BRANCH=${LABELDESK_BRANCH:-main}
die() { echo "✗ $1" >&2; exit "${2:-1}"; }
want=${1:-}; want=${want#v}; everyone=${2:-}
[ -n "$want" ] || die "which version? (a number like 0.8.1, or newest)"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "this copy isn't a git checkout — reinstall it from GitHub"
[ -z "$(git status --porcelain --untracked-files=no)" ] || die "this PC has changes of its own that aren't sent yet — run tools/update.sh first"
git fetch --quiet --tags "$REMOTE" "$BRANCH" || die "couldn't reach GitHub"
[ "$(git rev-list --count "$REMOTE/$BRANCH..HEAD")" = 0 ] || die "this PC has commits that aren't on GitHub — run tools/update.sh first"

hold() { # remember (or forget) the held version in this PC's config.json — LabelDesk then shows no update notices
  python3 - "$1" <<'PY'
import json, os, sys
f = os.path.expanduser("~/Library/Application Support/LabelDesk/config.json" if sys.platform == "darwin" else "~/.config/labeldesk/config.json")
try:
    c = json.load(open(f))
except (OSError, ValueError):
    c = {}
if sys.argv[1]:
    c["hold_version"] = sys.argv[1]
else:
    c.pop("hold_version", None)
os.makedirs(os.path.dirname(f), exist_ok=True)
json.dump(c, open(f + ".tmp", "w"), indent=2); os.replace(f + ".tmp", f)
PY
}
restart() {
  if [ -f ~/.config/systemd/user/labeldesk.service ] || [ -f ~/Library/LaunchAgents/com.labeldesk.app.plist ]; then
    tools/install-app.sh
  fi
}

if [ "$want" = newest ]; then
  git checkout --quiet "$BRANCH" 2>/dev/null || true
  git reset --quiet --hard "$REMOTE/$BRANCH"
  hold ""
  echo "✓ this PC is on the newest version again: $(tr -d '[:space:]' < VERSION)"
  restart; exit 0
fi

git rev-parse -q --verify "refs/tags/v$want" >/dev/null || die "there's no version $want on GitHub"
if [ "$everyone" = --everyone ]; then
  git merge --quiet --ff-only "$REMOTE/$BRANCH"                 # the newest rollback tool (it keeps itself)
  tools/rollback.sh "$want" "rolled back from Settings on $(hostname -s 2>/dev/null || hostname)"
  hold ""
  echo "✓ every PC goes back to the code of $want with its next update"
  restart; exit 0
fi
[ "$(uname)" != Darwin ] || [ "$(printf '%s\n0.8.0\n' "$want" | sort -t. -k1,1n -k2,2n -k3,3n | head -1)" = 0.8.0 ] \
  || die "LabelDesk runs on the Mac since 0.8.0 — pick 0.8.0 or newer"
git checkout --quiet "$BRANCH" 2>/dev/null || true
git reset --quiet --hard "v$want"                                # main, at the older version (GitHub is untouched)
hold "$want"
echo "✓ this PC now runs LabelDesk $want and stays on it (Settings → Version → Back to the newest version)"
restart
