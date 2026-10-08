---
name: labeldesk-printer-setup
description: Install DYMO's 550-series CUPS driver and LabelDesk's printer queues, and fix printing (550 Turbo / 5XL, Fedora and Windows): nothing prints, wrong size, tiled, upside down, CUPS errors.
---

# Set up and troubleshoot the DYMO printers (Fedora)

## First-time setup (in order)
1. `tools/install-driver.sh` — builds DYMO's official LW5xx_Linux driver (pinned commit), installs `raster2dymolw_v2`,
   `lw550t.ppd`, `lw5xl.ppd`, and the SELinux module `dymo_cups`. Needs internet (GitHub) and sudo.
2. Find the printer IPs: `avahi-browse -rtp _pdl-datastream._tcp | grep -i dymo`, the router's DHCP list, or the
   printer's network status (the 550 series prints/shows it). Give them fixed IPs (DHCP reservation) if possible.
3. `tools/add-printers.sh <550T-ip> <5XL-ip>` — queues `Dymo-550-Turbo` (page w102h252) and `Dymo-5XL`
   (page 1744907_4_in_x_6_in) on `socket://IP:9100`. It warns if port 9100 doesn't answer.
4. `tools/install-app.sh` — service + app-menu entry; open http://127.0.0.1:8792.
5. Print one tag, check direction (Rotate 180° if needed), then one shipping label.

## When a label doesn't print — start with `tools/doctor.sh` (add `--fix` to repair), then check in this order
```bash
lpstat -t                                    # queues enabled? jobs stuck? printer state message
journalctl -u cups --since "-10 min" -o cat | grep -E "Job [0-9]+\]" | grep -iE "error|xpages|cupsWidth|lock|status|ready"
sudo ausearch -m avc -ts recent | grep raster2dymo      # SELinux denials
timeout 3 bash -c "echo > /dev/tcp/<ip>/9100" && echo port-open
```
| Symptom | Cause | Fix |
|---|---|---|
| "Unable to get synchronization lock: Permission denied" | SELinux blocks /dev/shm semaphore | reinstall `tools/selinux/dymo_cups.te` (install-driver.sh does it); add any newly denied permission shown by ausearch |
| Label printed at half size / spread over several labels; journal `xpages = 2x…` | image bigger than the PPD ImageableArea → CUPS tiles | canvas must be floor(area × 300) − 1 px (tag 391×960, ship 1199×1799); never full-label size |
| "Printer is not ready" / "ReadStatus TIMEOUT" | driver's status handshake got no reply | real printer: check IP/port/power, labels loaded, genuine DYMO roll (NFC chip). With a fake listener this is expected |
| `lp: The printer or class does not exist` | queue missing / different name | run add-printers.sh, or set tag_queue/ship_queue in ~/.config/labeldesk/config.json |
| Tag upside down | feed direction | "Rotate 180°" under the preview (per browser) or `"flip_tag": true` in config.json |
| Blank label / nothing on a non-DYMO roll | 550 series refuses non-genuine labels | use DYMO labels |

Print quality/density: PPD options `DymoPrintQuality`, `DymoPrintDensity`, `DymoHalftoning` —
`lpoptions -p Dymo-550-Turbo -l` lists them; set defaults with `lpadmin -p Dymo-550-Turbo -o Option=Value`.
Never disable SELinux to make printing work.

# Windows: the printers can't be added or found (e.g. the PC is on Wi-Fi)
The Windows build prints through DYMO Connect's driver to the same network printers (they're on Ethernet). Don't guess
the cause: collect facts first, then change one thing, reversibly.
1. LabelDesk → Settings → **DYMO printers by IP** → Check (same script), or `windows/printer-check.ps1 -PrinterIP <550T-ip>,<5XL-ip>` (read-only, no admin; also installed beside LabelDesk in
   %LOCALAPPDATA%\Programs\LabelDesk). It reports: Wi-Fi vs wired + IP/subnet, the network profile (Public = network
   discovery off), ping and tcp 9100/631/80 to each printer, same-subnet or not, DYMO drivers, existing DYMO printers/ports.
2. Read the result:
   | Result | Means | Next |
   |---|---|---|
   | tcp 9100 open, but discovery/"Add printer" finds nothing | discovery (mDNS/WSD) doesn't reach this PC: Public profile, or Wi-Fi on another subnet/VLAN | add by IP: Settings → Add 550 Turbo / Add 5XL, or `windows/add-dymo-printer.ps1 -Model 550 -IP …` (admin; `-Remove` undoes it) |
   | ping/9100 no answer, different subnet | Wi-Fi network can't route to the printers' network (guest Wi-Fi, VLAN, client isolation) | network fix (router/AP rules or put the PC on the printers' network); a printer added by IP would not print either |
   | ping/9100 no answer, same subnet | printer off/asleep, wrong IP, or AP client isolation | check the IP on the printer; try from a wired PC to tell the two apart |
   | no DYMO drivers | DYMO Connect not installed | install DYMO Connect, then add the printer |
   | printer exists but its port host is an old IP | DHCP gave the printer a new address | `-Remove`, add again with the new IP; give the printer a DHCP reservation |
3. LabelDesk finds printers by name ("550"+"turbo", "5xl") or by DYMO driver name, so any of these names work.
