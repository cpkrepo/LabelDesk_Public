# shared by the tools/mac scripts (bash 3.2 — what macOS ships)
PPDS=/Library/Printers/PPDs/Contents/Resources
DYMO_FILTER=/Library/Printers/DYMO/Filters/V2/raster2dymolw
PLIST=~/Library/LaunchAgents/com.labeldesk.app.plist
APP=~/Applications/LabelDesk.app
DATA_DIR=~/Library/"Application Support"/LabelDesk
LOG=~/Library/Logs/LabelDesk.log
URL=http://127.0.0.1:8792
DYMO_DOWNLOAD=https://www.dymo.com/support?cfid=online-support-sw-downloads
with_timeout() { local s=$1; shift; perl -e 'alarm shift; exec @ARGV' "$s" "$@"; }   # no `timeout` on macOS
answers() { nc -z -G 3 "$1" "$2" >/dev/null 2>&1; }                                     # host port
driver_ok() { [ -f "$PPDS/lw550t.ppd.gz" ] && [ -f "$PPDS/lw5xl.ppd.gz" ] && [ -x "$DYMO_FILTER" ]; }
model_for() { lpinfo -m 2>/dev/null | awk -v m="$1.ppd" 'index($1, m) {print $1; exit}'; }   # lw550t → its lpinfo name
