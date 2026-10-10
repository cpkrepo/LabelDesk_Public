#!/bin/bash
# macOS: run LabelDesk for this user — a LaunchAgent (starts at login, restarts if it dies) running server/app.py from
# THIS checkout, and ~/Applications/LabelDesk.app (Launchpad / Spotlight / Dock) that opens it in the browser.
#   tools/install-app.sh            install / update (update.sh re-runs it)
#   tools/install-app.sh --remove   uninstall (history and settings stay in ~/Library/Application Support/LabelDesk)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); . "$here/common.sh"
repo=$(cd "$here/../.." && pwd)
uid=$(id -u)
if [ "${1:-}" = "--remove" ]; then
  launchctl bootout "gui/$uid" "$PLIST" 2>/dev/null || true
  rm -rf "$PLIST" "$APP"; echo "LabelDesk removed (history kept in $DATA_DIR)"; exit 0
fi
py=$(command -v python3 || true)
if [ -z "$py" ] || ! "$py" -c 'import sys; assert sys.version_info >= (3, 9)' 2>/dev/null; then
  echo "✗ python3 (3.9 or newer) is missing. Run:  xcode-select --install   then run this again."; exit 1
fi
command -v zbarimg >/dev/null || echo "  (optional) brew install zbar — a second barcode check; without it the browser checks barcodes"

mkdir -p "$(dirname "$PLIST")" "$DATA_DIR" "$(dirname "$LOG")"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.labeldesk.app</string>
  <key>ProgramArguments</key><array><string>$py</string><string>-u</string><string>$repo/server/app.py</string></array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PLIST
plutil -lint "$PLIST" >/dev/null

# the app: opens LabelDesk in its own window (Chrome/Edge/Brave --app) or the default browser
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/MacOS/LabelDesk" <<'RUN'
#!/bin/bash
url=http://127.0.0.1:8792
curl -sf --max-time 2 "$url/api/config" >/dev/null || launchctl kickstart "gui/$(id -u)/com.labeldesk.app" 2>/dev/null
for b in "Google Chrome" "Microsoft Edge" "Brave Browser" "Chromium"; do
  if [ -d "/Applications/$b.app" ] || [ -d "$HOME/Applications/$b.app" ]; then exec open -na "$b" --args --app="$url"; fi
done
exec open "$url"
RUN
chmod +x "$APP/Contents/MacOS/LabelDesk"
cat > "$APP/Contents/Info.plist" <<'INFO'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>LabelDesk</string>
  <key>CFBundleIdentifier</key><string>com.labeldesk.launcher</string>
  <key>CFBundleExecutable</key><string>LabelDesk</string>
  <key>CFBundleIconFile</key><string>LabelDesk</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><false/>
</dict></plist>
INFO
# icon from web/icon.svg (Quick Look renders the SVG; best effort — the app works without it)
tmp=$(mktemp -d)
if qlmanage -t -s 1024 -o "$tmp" "$repo/web/icon.svg" >/dev/null 2>&1 && [ -f "$tmp/icon.svg.png" ]; then
  mkdir "$tmp/LabelDesk.iconset"
  for s in 16 32 128 256 512; do
    sips -z $s $s "$tmp/icon.svg.png" --out "$tmp/LabelDesk.iconset/icon_${s}x${s}.png" >/dev/null
    sips -z $((s * 2)) $((s * 2)) "$tmp/icon.svg.png" --out "$tmp/LabelDesk.iconset/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$tmp/LabelDesk.iconset" -o "$APP/Contents/Resources/LabelDesk.icns" 2>/dev/null || true
fi
rm -rf "$tmp"

launchctl bootout "gui/$uid" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$uid" "$PLIST"
for _ in 1 2 3 4 5 6 7 8 9 10; do curl -sf --max-time 2 "$URL/api/config" >/dev/null && break; sleep 1; done
curl -sf --max-time 2 "$URL/api/config" >/dev/null && echo "LabelDesk running: $URL (Launchpad / Spotlight: LabelDesk)" \
  || { echo "didn't start — tail $LOG"; exit 1; }
