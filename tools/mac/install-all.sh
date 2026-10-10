#!/bin/bash
# One-shot macOS install from a clone: checks → printer queues → app → health check. Safe to re-run.
#   tools/install-all.sh                      finds the two DYMOs on the network by name
#   tools/install-all.sh <550T-ip> <5XL-ip>   or give their IPs
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); . "$here/common.sh"
echo "== 1/4 DYMO driver (DYMO Connect for Mac)"
if driver_ok; then echo "  installed"
else
  echo "  ✗ not installed. Download DYMO Connect for Mac (opening the page), install it, then run this again:"
  echo "    $DYMO_DOWNLOAD"; open "$DYMO_DOWNLOAD" 2>/dev/null || true; exit 1
fi
echo "== 2/4 printer queues";  "$here/add-printers.sh" "$@"
echo "== 3/4 LabelDesk app";   "$here/install-app.sh"
echo "== 4/4 health check";    "$here/doctor.sh" || echo "(see above — 'tools/doctor.sh --fix' repairs the safe things)"
