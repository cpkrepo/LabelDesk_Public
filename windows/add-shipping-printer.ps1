# Adds the printer "Shipping Label (LabelDesk)" on this Windows PC: print a UPS/FedEx label page to it from any
# browser and it opens in LabelDesk — found, turned upright, ready for the 5XL. Uses Windows' own
# "Microsoft Print to PDF" driver with a file port in LabelDesk's inbox. Adding printers needs admin rights, so this
# runs elevated (the Start-menu entry "LabelDesk – add Shipping Label printer" asks via UAC).
param([string]$User = $env:USERNAME, [string]$Inbox = "$env:LOCALAPPDATA\LabelDesk\inbox")
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $Inbox | Out-Null
$port = Join-Path $Inbox "print-dialog.pdf"
if (-not (Get-PrinterPort -Name $port -ErrorAction SilentlyContinue)) { Add-PrinterPort -Name $port }
if (Get-Printer -Name "Shipping Label (LabelDesk)" -ErrorAction SilentlyContinue) { Remove-Printer -Name "Shipping Label (LabelDesk)" }
Add-Printer -Name "Shipping Label (LabelDesk)" -DriverName "Microsoft Print To PDF" -PortName $port
Write-Host "Added 'Shipping Label (LabelDesk)' → $port"
