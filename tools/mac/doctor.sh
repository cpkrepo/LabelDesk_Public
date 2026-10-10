#!/bin/bash
# macOS health check — run it when something doesn't print. --fix resumes paused queues and restarts the app.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd); . "$here/common.sh"
fix=0; [ "${1:-}" = "--fix" ] && fix=1
bad=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n      → %s\n' "$1" "$2"; bad=$((bad + 1)); }

echo "Driver"
driver_ok && ok "DYMO's 550-series driver installed (DYMO Connect for Mac)" \
  || fail "DYMO's driver missing" "install DYMO Connect for Mac: $DYMO_DOWNLOAD"

echo "CUPS"
lpstat -r >/dev/null 2>&1 && ok "printing system running" || fail "CUPS not answering" "restart the Mac"
for q in Dymo-550-Turbo Dymo-5XL; do
  if ! lpstat -p "$q" >/dev/null 2>&1; then fail "queue $q missing" "tools/add-printers.sh"; continue; fi
  line=$(lpstat -p "$q" | head -1); uri=$(lpstat -v "$q" | sed 's/.*: //')
  if echo "$line" | grep -q disabled || lpstat -a "$q" 2>/dev/null | grep -q 'not accepting'; then
    if [ $fix = 1 ]; then cupsenable "$q"; cupsaccept "$q"; ok "$q resumed"; else fail "$q is paused" "tools/doctor.sh --fix (or Resume in LabelDesk)"; fi
  else ok "$q ready ($uri)"; fi
  case $uri in
    socket://*) h=${uri#socket://}; p=${h##*:}; h=${h%:*}
      answers "$h" "$p" && ok "  printer at $h:$p answers" \
        || fail "  printer at $h:$p not answering" "check power / network cable; if its IP changed: tools/add-printers.sh";;
    dnssd://*) with_timeout 10 lpinfo --include-schemes dnssd -v 2>/dev/null | grep -qF "${uri%%\?*}" && ok "  printer found on the network" \
        || fail "  printer not visible on the network" "check power / network cable";;
  esac
done
stuck=$(lpstat -o 2>/dev/null | grep -cE '^(Dymo-550-Turbo|Dymo-5XL)-' || true)
[ "${stuck:-0}" -gt 0 ] && echo "  · $stuck job(s) waiting in the queues: lpstat -o   (cancel all: cancel -a Dymo-5XL)"

echo "LabelDesk"
command -v python3 >/dev/null && ok "python3 present" || fail "python3 missing" "xcode-select --install"
command -v zbarimg >/dev/null && ok "zbar present (second barcode check)" || echo "  · no zbar — the browser checks barcodes (optional: brew install zbar)"
if launchctl print "gui/$(id -u)/com.labeldesk.app" >/dev/null 2>&1; then ok "LaunchAgent loaded"
elif [ $fix = 1 ]; then "$here/install-app.sh" >/dev/null && ok "app reinstalled"
else fail "LaunchAgent not loaded" "tools/doctor.sh --fix (or tools/install-app.sh)"; fi
v=$(curl -sf --max-time 3 "$URL/api/config" | sed -n 's/.*"version": "\([^"]*\)".*/\1/p')
if [ -n "$v" ]; then ok "app answering (v$v) — $URL"
elif [ $fix = 1 ]; then launchctl kickstart -k "gui/$(id -u)/com.labeldesk.app" && sleep 2 && ok "app restarted"
else fail "app not answering on :8792" "tail -30 $LOG"; fi

echo
[ $bad = 0 ] && echo "All good." || { echo "$bad problem(s)."; [ $fix = 0 ] && echo "Try: tools/doctor.sh --fix"; }
exit $(( bad > 0 ))
