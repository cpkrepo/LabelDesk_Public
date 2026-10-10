#!/usr/bin/env bash
# Install DYMO's official CUPS driver for the LabelWriter 550 / 550 Turbo / 5XL on Fedora (tested on Fedora 44).
# Fedora's own dymo-cups-drivers package is 1.4.0.5 — 4xx series only, no 550 series. This builds DYMO's newer
# source (github.com/dymosoftware/Drivers, LW5xx_Linux) and installs raster2dymolw_v2 + lw550t.ppd / lw5xl.ppd.
# Two fixes needed on a current Fedora: boost-devel (the source bundles only part of Boost) and "-include ctime"
# (their code uses time()/difftime() without #include <ctime>, which new GCC rejects).
[ "$(uname)" = Darwin ] && { echo "On a Mac the driver comes with DYMO Connect for Mac — tools/install-all.sh checks for it"; exit 0; }
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
COMMIT=${DYMO_DRIVERS_COMMIT:-9f2f15b3f1c2dddf4dcdfb64f380748120d249ba}     # pinned: the commit this was tested with
sudo dnf install -y cups cups-devel gcc-c++ autoconf automake libtool boost-devel git poppler-utils
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
git clone -q https://github.com/dymosoftware/Drivers "$work/Drivers"
git -C "$work/Drivers" checkout -q "$COMMIT"
cd "$work/Drivers/LW5xx_Linux"
autoreconf -fi >/dev/null 2>&1 || true
./configure --prefix=/usr >/dev/null
make -j"$(nproc)" CXXFLAGS="-O2 -include ctime" >"$work/build.log" 2>&1 || { tail -25 "$work/build.log"; exit 1; }   # old C++: many deprecation warnings
sudo make install >/dev/null
# SELinux (enforcing on Fedora) blocks the filter's print lock in /dev/shm — install the narrow policy module
if command -v getenforce >/dev/null && [ "$(getenforce)" != Disabled ]; then
  sudo dnf install -y -q checkpolicy policycoreutils >/dev/null
  checkmodule -M -m -o "$work/dymo_cups.mod" "$here/selinux/dymo_cups.te"
  semodule_package -o "$work/dymo_cups.pp" -m "$work/dymo_cups.mod"
  sudo semodule -i "$work/dymo_cups.pp"
fi
sudo systemctl restart cups
ls /usr/lib/cups/filter/raster2dymolw_v2 /usr/share/cups/model/lw550t.ppd* /usr/share/cups/model/lw5xl.ppd* >/dev/null
echo "DYMO 550-series driver installed (commit ${COMMIT:0:10}). Next: tools/add-printers.sh"
