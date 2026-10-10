#!/usr/bin/env bash
# Create the CUPS queues LabelDesk uses:
#   Dymo-550-Turbo      LabelWriter 550 Turbo · inventory tags · 30252 Address (1-1/8" × 3-1/2"; LabelDesk sets the page per print)
#   Dymo-5XL            LabelWriter 5XL       · shipping labels · 1744907 (4" × 6")
#   LabelDesk-Shipping  "Shipping Label (LabelDesk)" — print a carrier's label page to it from any app; it opens in
#                       LabelDesk found, upright and ready (tools/cups/labeldesk backend → /var/spool/labeldesk)
# Usage:  tools/add-printers.sh                    # find the DYMOs on the network by name (recommended)
#         tools/add-printers.sh <550T-ip> <5XL-ip> # or fixed IPs (then give the printers DHCP reservations)
# By name (Bonjour/dnssd) the queues keep working when a printer gets a new IP; raw port 9100 underneath.
[ "$(uname)" = Darwin ] && exec "$(dirname "$0")/mac/add-printers.sh" "$@"   # macOS: tools/mac/
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
PORT=${DYMO_PORT:-9100}
ppd() { ls /usr/share/cups/model/"$1".ppd* 2>/dev/null | head -1; }
[ -n "$(ppd lw550t)" ] && [ -n "$(ppd lw5xl)" ] || { echo "Driver missing — run tools/install-driver.sh first"; exit 1; }

t_uri=""; x_uri=""
if [ $# -ge 2 ]; then
  t_uri="socket://$1:$PORT"; x_uri="socket://$2:$PORT"
else
  echo "Looking for DYMO printers on the network (15 s)…"
  found=$(timeout 20 lpinfo --include-schemes dnssd -v 2>/dev/null | awk '{print $2}' | grep -i -E 'dymo|labelwriter' || true)
  t_uri=$(echo "$found" | grep -i '550' | grep -i turbo | head -1)
  x_uri=$(echo "$found" | grep -i '5xl' | head -1)
  [ -n "$found" ] && echo "$found" | sed 's/^/  found: /'
  if [ -z "$t_uri" ]; then read -rp "550 Turbo not found by name — its IP address: " ip; t_uri="socket://$ip:$PORT"; fi
  if [ -z "$x_uri" ]; then read -rp "5XL not found by name — its IP address: " ip; x_uri="socket://$ip:$PORT"; fi
fi
for u in "$t_uri" "$x_uri"; do
  case $u in socket://*) h=${u#socket://}; h=${h%:*}
    timeout 3 bash -c "echo > /dev/tcp/$h/$PORT" 2>/dev/null && echo "  $h:$PORT answers" \
      || echo "  WARNING: $h:$PORT not answering (printer off, wrong IP, or another port — DYMO_PORT=…)";; esac
done
sudo lpadmin -p Dymo-550-Turbo -E -v "$t_uri" -m "$(basename "$(ppd lw550t)")" \
  -D "DYMO LabelWriter 550 Turbo (inventory tags)" -o PageSize=w79h252 -o printer-error-policy=abort-job 2>/dev/null
sudo lpadmin -p Dymo-5XL -E -v "$x_uri" -m "$(basename "$(ppd lw5xl)")" \
  -D "DYMO LabelWriter 5XL (shipping)" -o PageSize=1744907_4_in_x_6_in -o printer-error-policy=abort-job 2>/dev/null

# the print-dialog printer: backend + spool folder (SELinux: CUPS may write print_spool_t)
sudo install -m 0755 "$here/cups/labeldesk" /usr/lib/cups/backend/labeldesk
sudo install -d -m 1777 /var/spool/labeldesk
if command -v getenforce >/dev/null && [ "$(getenforce)" != Disabled ]; then
  command -v semanage >/dev/null || sudo dnf install -y -q policycoreutils-python-utils
  sudo semanage fcontext -a -t print_spool_t '/var/spool/labeldesk(/.*)?' 2>/dev/null \
    || sudo semanage fcontext -m -t print_spool_t '/var/spool/labeldesk(/.*)?'
  sudo restorecon -R /var/spool/labeldesk
fi
sudo lpadmin -p LabelDesk-Shipping -E -v labeldesk:/ -m raw -D "Shipping Label (LabelDesk)" \
  -L "opens in LabelDesk, ready to print on the 5XL" 2>/dev/null
lpstat -v Dymo-550-Turbo Dymo-5XL LabelDesk-Shipping
echo "Queues ready. Check everything with tools/doctor.sh"
