#!/usr/bin/env bash
# One-shot Fedora install from an unpacked LabelDesk folder (or a checkout): DYMO driver → printer queues → app.
#   tools/install-all.sh                      # finds the two DYMOs on the network by name
#   tools/install-all.sh <550T-ip> <5XL-ip>   # or give their IPs
# Needs sudo (asks once per step) and internet (DYMO's driver source comes from github.com/dymosoftware).
# Safe to re-run. Afterwards: app menu → LabelDesk, or http://127.0.0.1:8792.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== 1/4 DYMO 550-series driver";  tools/install-driver.sh
echo "== 2/4 printer queues";          tools/add-printers.sh "$@"
echo "== 3/4 LabelDesk app";           tools/install-app.sh
echo "== 4/4 health check";            tools/doctor.sh || echo "(see above — 'tools/doctor.sh --fix' repairs the safe things)"
