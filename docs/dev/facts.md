# LabelDesk — hard-won facts (driver, SELinux, CUPS, detection)

## Hard-won facts (each cost time — keep them true)
1. **Driver** (macOS: DYMO Connect for Mac's, same PPD pages/areas — docs/dev/mac.md)**:** Fedora's `dymo-cups-drivers` (1.4.0.5) has NO 550 series. Use DYMO's own source
   (github.com/dymosoftware/Drivers → `LW5xx_Linux`, pinned commit in install-driver.sh). On current Fedora it needs
   `boost-devel` and `CXXFLAGS="-O2 -include ctime"`. Filter: `raster2dymolw_v2`; PPDs `lw550t.ppd`, `lw5xl.ppd`.
2. **SELinux** (enforcing) blocks the filter's print lock (boost named_mutex → `/dev/shm/sem.*`): every job fails with
   "Unable to get synchronization lock: Permission denied". Fix = `tools/selinux/dymo_cups.te` (cupsd_t → tmpfs_t file:
   create/open/read/write/unlink/getattr/map/lock/link/rename/setattr). Never "fix" by disabling SELinux. Check with
   `sudo ausearch -m avc -ts recent | grep raster2dymo`.
3. **Image size = the PPD's ImageableArea, not the label size.** A full-label image (425 × 1046) is larger than the
   printable area and CUPS **tiles it over 2 × 2 pages** (journal: `xpages = 2x…`). Canvas = floor(area × 300) − 1 px:
   tag 298 × 962 (30252; 30321: 391 × 960), shipping 1199 × 1799; printed with `lp -o PageSize=… -o ppi=300 -o position=center`.
4. **The 550 driver is bidirectional** (Fedora filter AND the Windows language monitor): before each page it sends
   `ESC A <n>` and waits for a 32-byte status. A dumb listener only ever gets those 3 bytes → "Printer is not ready"
   (Fedora) / job stuck "Printing" then Error (Windows). `tests/fake_labelwriter.py` answers it (byte 10 = 8, media OK;
   Windows needs that, all-zeros isn't enough) and decodes each job's `ESC D` raster bands to a PBM — the label exactly
   as it would print. Verified 2026-09-30 on both platforms: tag 392×907 (Win) / 392×930 (Fedora), same orientation;
   5XL 4×6 1200×1800 in two bands. The DYMO Windows monitor takes ~8–10 s per label (built-in waits). Still to verify
   against the REAL printers over Ethernet (see Open items).
5. CUPS prints "Printer drivers are deprecated" when adding PPD queues — a notice about future CUPS 3; works on F44.
6. Genuine DYMO labels only: the 550 series reads the roll's NFC chip. Third-party rolls won't print — not a bug here.
7. **Shipping-label detection (detect.js)**, built against REAL pages (kept out of git — real addresses): 2 UPS letter/A4
   pages (label with a thin black border, turned sideways, + instructions + dotted fold line + browser URL/date),
   2 FedEx Ship Manager "Print Your Label(s)" pages and the FedEx Ground test page (NO border, turned the other way),
   1 scanned FedEx page (upright, instructions down the side). All six: whole label found, instructions left out, upright.
   - Bordered: largest rectangle of THIN dark lines (dotted lines and filled dark areas rejected).
   - Borderless: biggest cluster of dense graphics (1D bars, 2D codes, logo blocks), grown until a gap of 5 % of the page
     (FedEx: gaps inside a label reach 0.37", instructions start ≥ 1" away), then thin text-only edge strips set apart
     by ≥ 2 % are trimmed (the browser's date/title line sits 0.25" above FedEx labels).
   - Upright: the main tracking barcode is at the BOTTOM of UPS and FedEx labels → turn so the bar cells' centre of
     mass is at the bottom. UPS pages turn 90° clockwise, FedEx 270°. User can override (↺ ↻ 180°) or drag a box.
8. **"Printed" means the printer finished**: every job is followed through IPP (Get-Job-Attributes). A job that ends
   stopped/aborted is cancelled so it can't print unexpectedly later; the UI offers Print again / Resume. The DYMO
   filter raises com.dymo.busy-error when its status request gets no answer — so "Printer is not ready" is explained
   as "isn't answering", not "busy". Users can cupsenable/cupsaccept without sudo (Fedora: wheel).
9. Barcode check before printing a shipping label (zbar). Verified on real UPS + FedEx labels at 300 dpi; a blurred
   copy is refused (422) with "Print anyway". The FedEx tracking number = last 12 digits of the 34-digit barcode.
10. Headless Chrome quirk: createImageBitmap()/img.decode() of large images can stall under --virtual-time-budget —
   test detection with Node (tests/detect.test.mjs) and UI wiring with canvas-drawn pages (tests/render/ship.js). The app
   decodes with <img>.decode() (createImageBitmap hung even in real time there).
