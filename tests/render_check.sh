#!/usr/bin/env bash
# Render check without a printer: draw sample tags with the real app code in headless Chrome, then verify
#   · page size = the tag label's printable area at 300 dpi (30252: 298 × 962, 30321: 391 × 960)   · the ticket barcode decodes (zbarimg)
# Writes the PNGs (turned to reading orientation) to ./render-out/ for a visual look.
# Needs: google-chrome (or chromium), python3-pillow, zbar.   Usage: tests/render_check.sh
set -euo pipefail
cd "$(dirname "$0")/.."
work=$(mktemp -d); out=render-out; mkdir -p "$out"
trap 'kill $pid 2>/dev/null || true; rm -rf "$work"' EXIT
cp -r web "$work/web"; cp tests/render/test.js "$work/web/"
sed -i 's#<script type="module" src="app.js"></script>#&<script type="module" src="test.js"></script>#' "$work/web/index.html"
# a stand-in shop logo (the real one is per PC, never in the repo) so the logo layout gets checked too
mkdir -p "$work/home/.config/labeldesk"
stock=${1:-30252}                         # tests/render_check.sh [30252|30321]
echo "{\"tag_label\": \"$stock\"}" > "$work/home/.config/labeldesk/config.json"
python3 -c "from PIL import Image, ImageDraw; im = Image.new('RGBA', (180, 200), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
d.rounded_rectangle((10, 40, 170, 190), 28, fill='black'); d.ellipse((40, 70, 80, 110), fill='white'); d.ellipse((100, 70, 140, 110), fill='white')
im.save('$work/home/.config/labeldesk/tag-logo.png')"
port=$((20000 + RANDOM % 20000))
HOME="$work/home" LABELDESK_WEB="$work/web" LABELDESK_DATA="$work/data" LABELDESK_PORT=$port python3 server/app.py >"$work/server.log" 2>&1 & pid=$!
sleep 1
chrome=$(command -v google-chrome || command -v chromium-browser || command -v chromium)
"$chrome" --headless=new --user-data-dir="$work/chrome" --virtual-time-budget=6000 --dump-dom "http://127.0.0.1:$port/" 2>/dev/null >"$work/dom.html"
python3 - "$work/dom.html" "$out" "$stock" <<'PY'
import base64, html, io, json, re, sys
from PIL import Image
d = json.loads(html.unescape(re.search(r'<pre id="out">(.*?)</pre>', open(sys.argv[1]).read(), re.S).group(1)))
assert d["c128_width_errors"] == 0, "Code 128 table has a pattern of the wrong width"
for k in ("tag", "long_bar", "contact_bar", "offset_bar", "template_bar", "template_c39", "template_qr", "blank", "intake_bar",
          "accessory_bar", "full_bar"):
    im = Image.open(io.BytesIO(base64.b64decode(d[k].split(",")[1])))
    want = {"30252": (298, 962), "30321": (391, 960)}[sys.argv[3]]
    assert im.size == want, f"{k}: {im.size} — must be the {sys.argv[3]} printable area {want} or CUPS tiles it"
    im.save(f"{sys.argv[2]}/{k}.png")
    im.rotate(90, expand=True).save(f"{sys.argv[2]}/{k}-reading.png")
for k, want in (("design_30336", (270, 592)), ("design_4x6", (1199, 1799))):     # floor(printable area × 300) − 1
    im = Image.open(io.BytesIO(base64.b64decode(d[k].split(",")[1])))
    assert im.size == want, f"{k}: {im.size}, want {want}"
    im.save(f"{sys.argv[2]}/{k}.png")
print(f"sizes OK ({sys.argv[3]} printable area)")
PY
for k in long_bar contact_bar offset_bar template_bar intake_bar accessory_bar full_bar; do
  zbarimg --quiet "$out/$k.png" | grep -qx "CODE-128:75013" && echo "barcode OK on $k (CODE-128:75013)" || { echo "barcode did NOT decode on $k"; exit 1; }
done
zbarimg --quiet "$out/template_c39.png" | grep -qx "CODE-39:75013" && echo "barcode OK on template_c39 (CODE-39:75013)" || { echo "Code 39 did NOT decode"; exit 1; }
zbarimg --quiet "$out/template_qr.png" | grep -qx "QR-Code:75013" && echo "barcode OK on template_qr (QR-Code:75013)" || { echo "QR did NOT decode"; exit 1; }
zbarimg --quiet "$out/design_30336.png" | grep -qx "CODE-128:75013" && echo "barcode OK on design_30336 (CODE-128:75013)" || { echo "designer 30336 barcode did NOT decode"; exit 1; }
zbarimg --quiet "$out/design_4x6.png" | grep -qx "QR-Code:https://example.com/t/75013" && echo "barcode OK on design_4x6 (QR)" || { echo "designer 4x6 QR did NOT decode"; exit 1; }
echo "images: $out/"
