#!/usr/bin/env bash
# LabelDesk health check — run it when something doesn't print, and after Fedora upgrades.
# Checks each piece in order and says exactly what's wrong; with --fix it repairs what's safe to repair
# (SELinux rule, paused queues, the app service). Nothing is changed without --fix.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd); fix=0; [ "${1:-}" = "--fix" ] && fix=1
bad=0
ok()   { printf '  \e[32m✓\e[0m %s\n' "$1"; }
fail() { printf '  \e[31m✗\e[0m %s\n      → %s\n' "$1" "$2"; bad=$((bad + 1)); }
note() { printf '  · %s\n' "$1"; }

echo "Driver"
if [ -x /usr/lib/cups/filter/raster2dymolw_v2 ] && ls /usr/share/cups/model/lw550t.ppd* /usr/share/cups/model/lw5xl.ppd* >/dev/null 2>&1; then
  ok "DYMO 550-series driver installed"
else fail "DYMO 550-series driver missing" "tools/install-driver.sh"; fi

echo "SELinux"
if ! command -v getenforce >/dev/null || [ "$(getenforce)" = Disabled ]; then note "SELinux off — nothing to check"
elif sudo -n semodule -l 2>/dev/null | grep -q '^dymo_cups' || semodule -l 2>/dev/null | grep -q '^dymo_cups'; then
  ok "dymo_cups policy loaded"
else
  if [ $fix = 1 ]; then w=$(mktemp -d); checkmodule -M -m -o "$w/dymo_cups.mod" "$here/selinux/dymo_cups.te" >/dev/null &&
    semodule_package -o "$w/dymo_cups.pp" -m "$w/dymo_cups.mod" && sudo semodule -i "$w/dymo_cups.pp" && ok "dymo_cups policy reinstalled"; rm -rf "$w"
  else fail "dymo_cups SELinux policy not loaded — every job would fail with 'synchronization lock'" "tools/doctor.sh --fix"; fi
fi
den=$(sudo -n ausearch -m avc -ts recent 2>/dev/null | grep -c raster2dymo || true)
[ "${den:-0}" -gt 0 ] && fail "$den SELinux denials for the DYMO filter in the last 10 min" "sudo ausearch -m avc -ts recent | grep raster2dymo — add the permission to tools/selinux/dymo_cups.te"

echo "CUPS"
systemctl is-active --quiet cups && ok "CUPS running" || fail "CUPS not running" "sudo systemctl enable --now cups"
for q in Dymo-550-Turbo Dymo-5XL LabelDesk-Shipping; do
  if ! lpstat -p "$q" >/dev/null 2>&1; then fail "queue $q missing" "tools/add-printers.sh"; continue; fi
  line=$(lpstat -p "$q" | head -1); uri=$(lpstat -v "$q" | sed 's/.*: //')
  if echo "$line" | grep -q disabled || lpstat -a "$q" 2>/dev/null | grep -q 'not accepting'; then
    if [ $fix = 1 ]; then cupsenable "$q"; cupsaccept "$q"; ok "$q resumed"; else fail "$q is paused" "tools/doctor.sh --fix (or Resume in LabelDesk)"; fi
  else ok "$q ready ($uri)"; fi
  case $uri in
    socket://*) h=${uri#socket://}; p=${h##*:}; h=${h%:*}
      timeout 3 bash -c "echo > /dev/tcp/$h/$p" 2>/dev/null && ok "  printer at $h:$p answers" \
        || fail "  printer at $h:$p not answering" "check power / network cable; if its IP changed: tools/add-printers.sh";;
    dnssd://*) timeout 10 lpinfo --include-schemes dnssd -v 2>/dev/null | grep -qF "${uri%%\?*}" && ok "  printer found on the network" \
        || fail "  printer not visible on the network" "check power / network cable";;
  esac
done
stuck=$(lpstat -o 2>/dev/null | grep -cE '^(Dymo-550-Turbo|Dymo-5XL)-' || true)
[ "${stuck:-0}" -gt 0 ] && note "$stuck job(s) waiting in the queues: lpstat -o   (cancel all: cancel -a Dymo-5XL)"
[ -d /var/spool/labeldesk ] && [ "$(stat -c %a /var/spool/labeldesk)" = 1777 ] && ok "print-dialog spool folder ok" \
  || fail "/var/spool/labeldesk missing or wrong permissions" "tools/add-printers.sh"

echo "LabelDesk"
for c in pdftoppm zbarimg lp; do command -v $c >/dev/null && ok "$c present" || fail "$c missing" "tools/install-app.sh"; done
if systemctl --user is-active --quiet labeldesk; then ok "service running"
elif [ $fix = 1 ]; then systemctl --user restart labeldesk && ok "service restarted"
else fail "service not running" "tools/doctor.sh --fix (or tools/install-app.sh)"; fi
v=$(curl -sf --max-time 3 http://127.0.0.1:8792/api/config | sed -n 's/.*"version": "\([^"]*\)".*/\1/p')
[ -n "$v" ] && ok "app answering (v$v) — http://127.0.0.1:8792" || fail "app not answering on :8792" "journalctl --user -u labeldesk -n 30"

echo
[ $bad = 0 ] && echo "All good." || { echo "$bad problem(s)."; [ $fix = 0 ] && echo "Try: tools/doctor.sh --fix"; }
exit $(( bad > 0 ))
