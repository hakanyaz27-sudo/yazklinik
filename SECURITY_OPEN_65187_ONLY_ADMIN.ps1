$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host "Yonetici olarak calistirin." -ForegroundColor Red
  exit 1
}

Set-NetFirewallProfile -Profile Domain,Private,Public -Enabled True -DefaultInboundAction Block -DefaultOutboundAction Allow -LogBlocked True

Get-NetFirewallRule -Direction Inbound -Action Allow -ErrorAction SilentlyContinue |
  Set-NetFirewallRule -Enabled False

Get-NetFirewallRule -DisplayName "YazKlinik D700 ONLY 65187 TCP Inbound" -ErrorAction SilentlyContinue |
  Remove-NetFirewallRule -ErrorAction SilentlyContinue

New-NetFirewallRule `
  -DisplayName "YazKlinik D700 ONLY 65187 TCP Inbound" `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort 65187 `
  -Profile Any `
  -EdgeTraversalPolicy Block `
  -Description "D700 security lockdown: only inbound TCP 65187 is allowed." | Out-Host

netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=65187 | Out-Null
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=65187 connectaddress=127.0.0.1 connectport=5443 | Out-Host

Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server" -Name "fDenyTSConnections" -Value 1
Disable-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue
Stop-Service -Name WinRM -Force -ErrorAction SilentlyContinue
Set-Service -Name WinRM -StartupType Disabled -ErrorAction SilentlyContinue

Write-Host "OK: sadece TCP 65187 inbound izinli." -ForegroundColor Green
Get-NetFirewallRule -Enabled True -Direction Inbound -Action Allow | Select-Object DisplayName,Profile,Direction,Action | Format-Table -AutoSize
pause

