# LabelDesk printer check for Windows: READ-ONLY. Changes nothing; no admin needed.
# Answers "why can't this PC add / reach the DYMO printers?" with facts instead of guesses:
#   - which network this PC is on (Wi-Fi or wired, IP + subnet, gateway) and whether Windows calls it Public
#     (a Public network profile turns network discovery off, so "find printers" comes up empty)
#   - for each printer IP you give: ping, and the ports the DYMO driver / web page use (9100 raw, 631 IPP, 80 web),
#     and whether the IP is on this PC's own subnet
#   - which DYMO drivers DYMO Connect installed, and which DYMO printers / ports already exist here
# Usage (PowerShell on the Windows PC):
#   powershell -ExecutionPolicy Bypass -File printer-check.ps1 -PrinterIP 192.0.2.10,192.0.2.11
# Without -PrinterIP it still reports the network, drivers and installed printers. Paste the whole output.
param([string[]]$PrinterIP = @())
$ErrorActionPreference = "Continue"
function Section($t) { Write-Host ""; Write-Host "==== $t" }

Section "This PC"
Write-Host ("{0}  Windows {1}  user {2}" -f $env:COMPUTERNAME, [Environment]::OSVersion.Version, $env:USERNAME)

Section "Network connections (up)"
$subnets = @()
foreach ($a in Get-NetAdapter | Where-Object Status -eq "Up") {
  $kind = if ($a.PhysicalMediaType -match "802\.11|Wireless" -or $a.Name -match "Wi-?Fi|Wireless") { "Wi-Fi" } else { "wired/other" }
  $cfg = Get-NetIPConfiguration -InterfaceIndex $a.ifIndex -ErrorAction SilentlyContinue
  $prof = Get-NetConnectionProfile -InterfaceIndex $a.ifIndex -ErrorAction SilentlyContinue
  foreach ($ip in @($cfg.IPv4Address)) {
    if (-not $ip) { continue }
    $subnets += [pscustomobject]@{ IP = $ip.IPAddress; Prefix = $ip.PrefixLength }
    Write-Host ("{0} [{1}]  {2}/{3}  gateway {4}  network '{5}' profile {6}" -f $a.Name, $kind, $ip.IPAddress, $ip.PrefixLength,
      ($cfg.IPv4DefaultGateway.NextHop -join ","), $prof.Name, $prof.NetworkCategory)
  }
  if ($prof.NetworkCategory -eq "Public") { Write-Host "   ! Profile is PUBLIC: network discovery is off on this connection, so printer discovery finds nothing." }
}

function InSubnet($ip, $net, $prefix) {
  $a = [BitConverter]::ToUInt32(([Net.IPAddress]::Parse($ip)).GetAddressBytes()[3..0], 0)
  $b = [BitConverter]::ToUInt32(([Net.IPAddress]::Parse($net)).GetAddressBytes()[3..0], 0)
  $mask = if ($prefix -eq 0) { 0 } else { [uint32]([math]::Pow(2, 32) - [math]::Pow(2, 32 - $prefix)) }
  return (($a -band $mask) -eq ($b -band $mask))
}

foreach ($p in $PrinterIP) {
  Section "Printer $p"
  $same = @($subnets | Where-Object { InSubnet $p $_.IP $_.Prefix })
  Write-Host ("same subnet as this PC: {0}" -f ($(if ($same) { "yes (" + $same[0].IP + ")" } else { "NO (traffic must be routed between networks)" })))
  $ping = Test-Connection -ComputerName $p -Count 2 -Quiet -ErrorAction SilentlyContinue
  Write-Host ("ping: {0}" -f $(if ($ping) { "answers" } else { "no answer" }))
  foreach ($port in 9100, 631, 80) {
    $c = New-Object Net.Sockets.TcpClient
    $ok = $false
    try { $ok = $c.ConnectAsync($p, $port).Wait(2000) -and $c.Connected } catch { $ok = $false } finally { $c.Close() }
    Write-Host ("tcp {0}: {1}" -f $port, $(if ($ok) { "open" } else { "no answer" }))
  }
}

Section "DYMO drivers on this PC (installed by DYMO Connect)"
$drv = @(Get-PrinterDriver -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "DYMO|LabelWriter" })
if ($drv) { $drv | ForEach-Object { Write-Host $_.Name } } else { Write-Host "none: install DYMO Connect first" }

Section "DYMO printers already added"
$prs = @(Get-Printer -ErrorAction SilentlyContinue | Where-Object { $_.DriverName -match "DYMO|LabelWriter" -or $_.Name -match "DYMO|LabelWriter" })
if (-not $prs) { Write-Host "none" }
foreach ($pr in $prs) {
  $port = Get-PrinterPort -Name $pr.PortName -ErrorAction SilentlyContinue
  Write-Host ("'{0}'  driver '{1}'  port '{2}'  host {3}:{4}  status {5}" -f $pr.Name, $pr.DriverName, $pr.PortName,
    $port.PrinterHostAddress, $port.PortNumber, $pr.PrinterStatus)
}
Write-Host ""
Write-Host "Done. Nothing was changed."
