# LabelDesk — Windows 11 build + test VM

## Windows 11 build (0.5)
Owner wants each PC **independent** (no shared server). Same app; only printing differs:
- `server/winprint.py`: DYMO's Windows driver (installed by **DYMO Connect**, which all coworkers have; same network
  printers) via ctypes — DEVMODE paper chosen by DYMO's paper name ("30321…", "1744907…/4 in x 6 in"), label drawn at
  its physical size centred (StretchDIBits, 8-bit grey DIB), job followed with GetJob (gone without error = printed),
  printer status via GetPrinter level 6. DEVMODEW offsets: dmFields @72, orientation @76, paper @78, copies @86.
  HDC restype must be c_void_p (64-bit). Printers found by name ("550"+"turbo", "5xl"), else by DYMO driver name (users
  rename them, e.g. "Asset Tags" / "Shipping Labels"); override tag_printer/ship_printer.
- The browser sends the label as **grey pixels** on Windows (pure-Python PNG decoding is too slow); `app.png_gray` only
  for reprints. PDFs → **pdf.js** and barcode checks → **ZXing** (web/vendor) in the browser on BOTH OSes; the server's
  zbar (Fedora) double-checks where present.
- Package: `tools/build-windows.sh` on Fedora → `dist/LabelDesk-<v>.msi` (wixl/msitools): per-user, no admin,
  %LOCALAPPDATA%\Programs\LabelDesk, embedded python.org Python 3.13.15 (sha256-pinned), Start menu "LabelDesk"
  (LabelDesk.pyw → server if needed + Edge --app window), Startup "LabelDesk (background)". Data %LOCALAPPDATA%\LabelDesk,
  config %APPDATA%\LabelDesk. wixl quirks: no RemoveFolder Directory=, no InstallPrivileges, heat needs -D Win64=yes.
- Print-dialog printer on Windows: Settings → "Add the Shipping Label printer" → elevated add-shipping-printer.ps1
  (Microsoft Print To PDF + file port %LOCALAPPDATA%\LabelDesk\inbox\print-dialog.pdf; inbox notices rewrites).
- Test VM: Windows 11 (QEMU, headless), DYMO Connect 1.5.1.20, printers → fake printer on the
  host (10.0.2.2:9100 — run tests/fake_labelwriter.py there). Drive the VM's desktop with a scheduled task
  (`-LogonType Interactive`) running PowerShell AppActivate/SendKeys/SetCursorPos — QEMU sendkey loses focus; Edge
  DevTools needs `--remote-debugging-port` AND a non-default `--user-data-dir`. Headless Chrome stalls on pdf.js workers / big image decodes — test browser paths in a real
  Chrome on Xvfb (`Xvfb :9` + `google-chrome --app=… ` + `import -window root`) or in Edge in the VM.
- Updates: Windows PCs run the MSI, not a git checkout. Each version tag makes GitHub Actions build the MSI
  (.github/workflows/windows-installer.yml, wixl on ubuntu-24.04) and attach LabelDesk-<v>.msi + .sha256 to the release.
  "Install update" downloads both, refuses a checksum mismatch, writes %LOCALAPPDATA%\LabelDesk\update\install-update.ps1,
  starts it detached and exits; the script waits for the server's PID, runs msiexec /i /qb (per user, no admin;
  RemoveExistingProducts replaces the old version) and starts labeldesk-server.pyw again. NOT yet run on Windows.
- Printers by IP: Settings → DYMO printers by IP runs printer-check.ps1 (read-only, output shown) and
  add-dymo-printer.ps1 -Pause in an elevated window. Both ship in the MSI root.

## Updates and version switching — tested on the VM 2026-10-10 (0.8.1 ⇄ 0.9.0)
- MSI upgrade bug (≤ 0.8.1 installers): files whose version didn't change (python.exe, pythonw.exe) were costed as
  "already there", then RemoveExistingProducts deleted them with the old product → LabelDesk installed without Python.
  Fix: `REINSTALLMODE=amus` in labeldesk.wxs (+ RemoveExistingProducts after InstallValidate). The NEW MSI's property
  governs, so upgrading any old install to ≥ 0.9.0 is fine.
- The update helper was started with DETACHED_PROCESS: PowerShell with no console quits at once, so "Install update"
  never ran msiexec. Now CREATE_NO_WINDOW | NEW_PROCESS_GROUP (+ BREAKAWAY_FROM_JOB, fallback without). PCs on ≤ 0.8.1
  can't self-update: run LabelDesk-0.9.0.msi by hand once.
- Per-user MSIs are NOT under HKCU…\Uninstall: find installs with `(New-Object -ComObject WindowsInstaller.Installer)
  .RelatedProducts('{6B9C2E31-…}')` (the fixed UpgradeCode). Older version = uninstall those, then install (an older MSI
  won't replace a newer one). Settings, logo, history in %APPDATA%/%LOCALAPPDATA%\LabelDesk survive.
- VM testing: start LabelDesk the way users do (explorer opening the Startup shortcut) — a scheduled task running
  pythonw directly kills its children when it exits. Send PowerShell scripts as ASCII files (PS 5 misreads UTF-8 without BOM).

