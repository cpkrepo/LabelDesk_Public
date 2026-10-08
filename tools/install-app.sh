#!/usr/bin/env bash
# Install LabelDesk for the current user: a systemd --user service (starts at login, restarts if it dies) running
# server/app.py from THIS checkout, plus an app-menu entry ("LabelDesk") that opens it in the browser.
#   tools/install-app.sh            install / update (re-run after `git pull`)
#   tools/install-app.sh --remove   uninstall
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
unit=~/.config/systemd/user/labeldesk.service
desk=~/.local/share/applications/labeldesk.desktop
if [ "${1:-}" = "--remove" ]; then
  systemctl --user disable --now labeldesk 2>/dev/null || true
  rm -f "$unit" "$desk"; systemctl --user daemon-reload; echo "LabelDesk removed (history kept in ~/.local/share/labeldesk)"; exit 0
fi
need=(); command -v pdftoppm >/dev/null || need+=(poppler-utils)             # PDF shipping labels
command -v zbarimg >/dev/null || need+=(zbar)                                 # barcode check before printing
command -v xdg-user-dir >/dev/null || need+=(xdg-user-dirs)                   # where Downloads is
[ ${#need[@]} -eq 0 ] || sudo dnf install -y "${need[@]}"
# its own window (no tabs / address bar) when a Chromium-family browser is installed; else the default browser
open="xdg-open http://127.0.0.1:8792"
for b in google-chrome google-chrome-stable chromium-browser chromium microsoft-edge brave-browser; do
  if command -v "$b" >/dev/null; then open="$b --app=http://127.0.0.1:8792 --class=LabelDesk"; break; fi
done
mkdir -p "$(dirname "$unit")" "$(dirname "$desk")"
cat > "$unit" <<UNIT
[Unit]
Description=LabelDesk — DYMO label printing (http://127.0.0.1:8792)
After=network-online.target cups.service

[Service]
ExecStart=/usr/bin/python3 -u $repo/server/app.py
Restart=on-failure

[Install]
WantedBy=default.target
UNIT
cat > "$desk" <<DESK
[Desktop Entry]
Type=Application
Name=LabelDesk
Comment=Print inventory tags and shipping labels on the DYMO printers
Exec=$open
StartupWMClass=LabelDesk
Icon=$repo/web/icon.svg
Categories=Office;Utility;
DESK
systemctl --user daemon-reload
systemctl --user enable --now labeldesk
systemctl --user restart labeldesk
sleep 1
curl -sf http://127.0.0.1:8792/api/config >/dev/null && echo "LabelDesk running: http://127.0.0.1:8792 (app menu: LabelDesk)" \
  || { echo "didn't start — journalctl --user -u labeldesk"; exit 1; }
