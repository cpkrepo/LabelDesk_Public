# Add a DYMO LabelWriter on this Windows PC by IP address: a Standard TCP/IP port (raw, 9100) + the DYMO driver that
# DYMO Connect installed. For PCs where DYMO Connect's / Windows' "find printers" can't see the printer (often a PC on
# Wi-Fi while the printers are wired, or a Public network profile). Run printer-check.ps1 first: this only helps when
# port 9100 answers from this PC. Needs admin (adding printers). Reversible: -Remove takes the printer and port out again.
#   powershell -ExecutionPolicy Bypass -File add-dymo-printer.ps1 -Model 550 -IP 192.0.2.10
#   powershell -ExecutionPolicy Bypass -File add-dymo-printer.ps1 -Model 5XL -IP 192.0.2.11
#   powershell -ExecutionPolicy Bypass -File add-dymo-printer.ps1 -Model 550 -Remove
# The names it uses ("DYMO LabelWriter 550 Turbo", "DYMO LabelWriter 5XL") are ones LabelDesk finds by itself.
param([Parameter(Mandatory = $true)][ValidateSet("550", "5XL")][string]$Model, [string]$IP, [switch]$Remove, [switch]$Pause)
# -Pause: keep the window open at the end (LabelDesk's Settings starts this in its own elevated window)
$ErrorActionPreference = "Stop"
if ($Pause) { trap { Write-Host "ERROR: $_"; Read-Host "Press Enter to close"; exit 1 } }
$name = if ($Model -eq "550") { "DYMO LabelWriter 550 Turbo" } else { "DYMO LabelWriter 5XL" }
$match = if ($Model -eq "550") { "550 Turbo" } else { "5XL" }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw "Run this from an administrator PowerShell (adding printers needs admin rights)." }

if ($Remove) {
  $p = Get-Printer -Name $name -ErrorAction SilentlyContinue
  if (-not $p) { Write-Host "No printer named '$name' here: nothing to remove."; exit 0 }
  $portName = $p.PortName
  Remove-Printer -Name $name
  if ($portName -like "LabelDesk_*" -and -not (Get-Printer | Where-Object PortName -eq $portName)) { Remove-PrinterPort -Name $portName }
  Write-Host "Removed '$name' (and its port $portName if nothing else used it)."
  if ($Pause) { Read-Host "Press Enter to close" }
  exit 0
}

if (-not $IP) { throw "Give the printer's IP: -IP 192.0.2.10 (find it on the printer's network status, or the router's DHCP list)." }
[void][Net.IPAddress]::Parse($IP)

$c = New-Object Net.Sockets.TcpClient
$open = $false
try { $open = $c.ConnectAsync($IP, 9100).Wait(3000) -and $c.Connected } catch { $open = $false } finally { $c.Close() }
if (-not $open) { throw "Port 9100 on $IP doesn't answer from this PC, so a printer added by IP couldn't print either. Run printer-check.ps1 -PrinterIP $IP and fix the network path first (nothing was changed)." }

$driver = Get-PrinterDriver | Where-Object { $_.Name -match "DYMO|LabelWriter" -and $_.Name -match [regex]::Escape($match) } | Select-Object -First 1
if (-not $driver) { throw "No DYMO $match driver on this PC. Install DYMO Connect first, then run this again (nothing was changed)." }

if (Get-Printer -Name $name -ErrorAction SilentlyContinue) { throw "A printer named '$name' already exists. Remove it first (-Remove) if it points at the wrong place." }
$portName = "LabelDesk_$IP"
if (-not (Get-PrinterPort -Name $portName -ErrorAction SilentlyContinue)) { Add-PrinterPort -Name $portName -PrinterHostAddress $IP -PortNumber 9100 }
Add-Printer -Name $name -DriverName $driver.Name -PortName $portName
Write-Host "Added '$name' -> ${IP}:9100 (driver '$($driver.Name)'). Print a test label from LabelDesk."
Write-Host "Give the printer a DHCP reservation so its IP doesn't change; if it does, run -Remove and add it again."
if ($Pause) { Read-Host "Press Enter to close" }
