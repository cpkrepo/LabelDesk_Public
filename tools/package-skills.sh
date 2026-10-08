#!/usr/bin/env bash
# Package the LabelDesk skills in .claude/skills/ for upload to Claude.ai (Customize → Skills → upload a ZIP):
# one ZIP per skill with the skill folder at the ZIP's root, which is the layout Claude.ai expects.
# Claude Code doesn't need this: it loads .claude/skills/ from the checkout by itself.
#   tools/package-skills.sh   →   dist/skills/<skill>.zip
set -euo pipefail
cd "$(dirname "$0")/.."
out=dist/skills; rm -rf "$out"; mkdir -p "$out"
for dir in .claude/skills/*/; do
  name=$(basename "$dir")
  desc=$(sed -n 's/^description: //p' "$dir/SKILL.md")
  [ "$(sed -n 's/^name: //p' "$dir/SKILL.md")" = "$name" ] || { echo "✗ $name: 'name:' in SKILL.md must match the folder name"; exit 1; }
  [ ${#desc} -le 200 ] || { echo "✗ $name: description is ${#desc} characters; Claude.ai allows 200"; exit 1; }
  (cd .claude/skills && zip -qr "../../$out/$name.zip" "$name")
  echo "✓ $out/$name.zip"
done
