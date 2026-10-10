#!/bin/bash
# macOS: the two CUPS queues LabelDesk prints to, on the driver that DYMO Connect for Mac installs (same page names
# and printable areas as DYMO's Linux driver — compared 2026-10-10).
#   Dymo-550-Turbo  LabelWriter 550 Turbo · inventory tags     Dymo-5XL  LabelWriter 5XL · 4" × 6" shipping labels
# Usage: tools/add-printers.sh                    find the DYMOs on the network by name (Bonjour)
#        tools/add-printers.sh <550T-ip> <5XL-ip> or fixed IPs (then give the printers DHCP reservations)
# No "Shipping Label (LabelDesk)" print-dialog printer on the Mac: in the print dialog choose PDF → Save as PDF to
# Downloads and LabelDesk opens it by itself.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); . "$here/common.sh"
PORT=${DYMO_PORT:-9100}
driver_ok || { echo "✗ DYMO's driver isn't installed. Install DYMO Connect for Mac first: $DYMO_DOWNLOAD"; exit 1; }

t_uri=""; x_uri=""
if [ $# -ge 2 ]; then
  t_uri="socket://$1:$PORT"; x_uri="socket://$2:$PORT"
else
  echo "Looking for DYMO printers on the network (15 s)…"
  found=$(with_timeout 20 lpinfo --include-schemes dnssd -v 2>/dev/null | awk '{print $2}' | grep -i -E 'dymo|labelwriter' || true)
  t_uri=$(echo "$found" | grep -i '550' | grep -i turbo | head -1 || true)
  x_uri=$(echo "$found" | grep -i '5xl' | head -1 || true)
  [ -z "$found" ] || echo "$found" | sed 's/^/  found: /'
  if [ -z "$t_uri" ]; then read -rp "550 Turbo not found by name — its IP address: " ip; t_uri="socket://$ip:$PORT"; fi
  if [ -z "$x_uri" ]; then read -rp "5XL not found by name — its IP address: " ip; x_uri="socket://$ip:$PORT"; fi
fi
for u in "$t_uri" "$x_uri"; do
  case $u in socket://*) h=${u#socket://}; h=${h%:*}
    answers "$h" "$PORT" && echo "  $h:$PORT answers" \
      || echo "  WARNING: $h:$PORT not answering (printer off, wrong IP, or another port — DYMO_PORT=…)";; esac
done
add() { # queue uri ppd description page
  local m; m=$(model_for "$3")
  if [ -n "$m" ]; then sudo lpadmin -p "$1" -E -v "$2" -m "$m" -D "$4" -o PageSize="$5" -o printer-error-policy=abort-job
  else sudo lpadmin -p "$1" -E -v "$2" -P "$PPDS/$3.ppd.gz" -D "$4" -o PageSize="$5" -o printer-error-policy=abort-job; fi
}
echo "Adding the queues (asks for your Mac password)…"
add Dymo-550-Turbo "$t_uri" lw550t "DYMO LabelWriter 550 Turbo (inventory tags)" w79h252
add Dymo-5XL "$x_uri" lw5xl "DYMO LabelWriter 5XL (shipping)" 1744907_4_in_x_6_in
lpstat -v Dymo-550-Turbo Dymo-5XL
echo "Queues ready. Check everything with tools/doctor.sh"
