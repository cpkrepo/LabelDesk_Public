#!/bin/bash
# Build the (unsigned) Mac installer package on a Mac: tools/mac/build-pkg.sh [--branch <branch>]  →  dist/LabelDesk-<v>.pkg
# It carries no app — its postinstall clones LabelDesk for the logged-in user (tools/mac/pkg/postinstall). Built for every
# release by .github/workflows/macos.yml. Unsigned: the first time, right-click → Open (or System Settings → Privacy &
# Security → Open Anyway).
set -euo pipefail
cd "$(dirname "$0")/../.."
branch=main; [ "${1:-}" = --branch ] && branch=$2
v=$(tr -d '[:space:]' < VERSION)
repo=${LABELDESK_REPO_URL:-https://github.com/cpkrepo/LabelDesk_Public.git}
work=$(mktemp -d); mkdir -p "$work/scripts" dist
sed -e "s|@REPO_URL@|$repo|" -e "s|@BRANCH@|$branch|" tools/mac/pkg/postinstall > "$work/scripts/postinstall"
chmod +x "$work/scripts/postinstall"
pkgbuild --nopayload --scripts "$work/scripts" --identifier com.labeldesk.installer --version "$v" "dist/LabelDesk-$v.pkg" >/dev/null
(cd dist && shasum -a 256 "LabelDesk-$v.pkg" > "LabelDesk-$v.pkg.sha256")
rm -rf "$work"
ls -la "dist/LabelDesk-$v.pkg"
