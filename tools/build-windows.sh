#!/usr/bin/env bash
# Build the Windows installer on Fedora:  tools/build-windows.sh  →  dist/LabelDesk-<version>.msi
# Per-user MSI (no admin rights): %LOCALAPPDATA%\Programs\LabelDesk with an embedded Python (python.org embeddable
# build, pinned + checksum-verified), the server, the web app, a Start-menu entry and a Startup entry (background server).
# Needs: msitools (wixl), curl, unzip, rsvg-convert or ImageMagick (icon).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=3.13.15
PY_SHA=d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf
VERSION=$(tr -d "[:space:]" < VERSION)
stage=build/windows/LabelDesk; rm -rf build/windows; mkdir -p "$stage" dist build/cache
zip=build/cache/python-$PY-embed-amd64.zip
[ -f "$zip" ] || curl -sfL -o "$zip" "https://www.python.org/ftp/python/$PY/python-$PY-embed-amd64.zip"
echo "$PY_SHA  $zip" | sha256sum -c --quiet
unzip -q "$zip" -d "$stage/python"
printf 'python313.zip\n.\n..\\server\n' > "$stage/python/python313._pth"          # LabelDesk's server modules
rsync -a --exclude __pycache__ server web "$stage/"
cp windows/LabelDesk.pyw windows/labeldesk-server.pyw windows/add-shipping-printer.ps1 windows/printer-check.ps1 windows/add-dymo-printer.ps1 "$stage/"
echo "$VERSION" > "$stage/VERSION"
# icon (.ico, several sizes) from web/icon.svg
if command -v rsvg-convert >/dev/null; then for s in 16 32 48 256; do rsvg-convert -w $s -h $s web/icon.svg -o build/windows/i$s.png; done
  magick build/windows/i{16,32,48,256}.png "$stage/icon.ico" 2>/dev/null || convert build/windows/i{16,32,48,256}.png "$stage/icon.ico"
else magick -background none web/icon.svg -define icon:auto-resize=256,48,32,16 "$stage/icon.ico"; fi
# the file list → WiX components, then the product
(cd build/windows && find LabelDesk -type f | sort | wixl-heat -p LabelDesk/ --directory-ref INSTALLDIR --component-group AppFiles \
   --var var.Src --win64 > files.wxs)
sed "s/@VERSION@/$VERSION/" windows/labeldesk.wxs > build/windows/labeldesk.wxs
wixl -a x64 -D Win64=yes -D Src="$PWD/build/windows/LabelDesk" -o "dist/LabelDesk-$VERSION.msi" build/windows/labeldesk.wxs build/windows/files.wxs
(cd dist && sha256sum "LabelDesk-$VERSION.msi" > "LabelDesk-$VERSION.msi.sha256")   # the app's one-click update checks it
ls -la "dist/LabelDesk-$VERSION.msi" "dist/LabelDesk-$VERSION.msi.sha256"
