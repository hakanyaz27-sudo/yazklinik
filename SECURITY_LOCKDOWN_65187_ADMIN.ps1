param(
  [int]$PublicPort = 65187,
  [int]$InternalPort = 5443
)

$ErrorActionPreference = "Stop"

function Test-IsAdmin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
  Write-Host "Bu script yonetici olarak calistirilmali." -ForegroundColor Red
  Write-Host "BAT dosyasini sag tiklayip 'Yonetici olarak calistir' secin." -ForegroundColor Yellow
  exit 1
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path $Root "security_backups\$Stamp"
$LogPath = Join-Path $BackupDir "lockdown_65187.log"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

Start-Transcript -Path $LogPath -Force | Out-Null

try {
  Write-Host "=== YazKlinik D700 Guvenlik Kilidi: sadece TCP $PublicPort acik ===" -ForegroundColor Cyan
  Write-Host "Backup klasoru: $BackupDir"

  $wfw = Join-Path $BackupDir "firewall-before-lockdown.wfw"
  netsh advfirewall export "$wfw" | Out-Host

  Get-NetFirewallProfile |
    Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction |
    Export-Csv -Path (Join-Path $BackupDir "firewall-profiles-before.csv") -NoTypeInformation -Encoding UTF8

  Get-NetFirewallRule -Direction Inbound |
    Select-Object DisplayName, Name, Enabled, Profile, Action, Direction |
    Export-Csv -Path (Join-Path $BackupDir "inbound-rules-before.csv") -NoTypeInformation -Encoding UTF8

  Get-NetTCPConnection -State Listen |
    Sort-Object LocalPort |
    Select-Object LocalAddress, LocalPort, OwningProcess |
    Export-Csv -Path (Join-Path $BackupDir "listening-ports-before.csv") -NoTypeInformation -Encoding UTF8

  Write-Host "Firewall profilleri aciliyor, varsayilan inbound BLOCK yapiliyor..."
  Set-NetFirewallProfile -Profile Domain,Private,Public `
    -Enabled True `
    -DefaultInboundAction Block `
    -DefaultOutboundAction Allow `
    -NotifyOnListen False `
    -AllowInboundRules True `
    -AllowLocalFirewallRules True `
    -LogBlocked True `
    -LogAllowed False `
    -LogMaxSizeKilobytes 32767 `
    -LogFileName "$env:SystemRoot\System32\LogFiles\Firewall\pfirewall.log"

  Write-Host "Mevcut tum inbound allow kurallari kapatiliyor..."
  Get-NetFirewallRule -Direction Inbound -Action Allow -ErrorAction SilentlyContinue |
    Set-NetFirewallRule -Enabled False

  Write-Host "Acil guvenli izin ekleniyor: TCP $PublicPort"
  Get-NetFirewallRule -DisplayName "YazKlinik D700 ONLY $PublicPort TCP Inbound" -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule -ErrorAction SilentlyContinue

  New-NetFirewallRule `
    -DisplayName "YazKlinik D700 ONLY $PublicPort TCP Inbound" `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $PublicPort `
    -Profile Any `
    -EdgeTraversalPolicy Block `
    -Description "D700 lockdown: dis erisim icin tek izinli inbound TCP portu." | Out-Host

  Write-Host "Uzak masaustu / WinRM / uzak yardim kapatiliyor..."
  Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server" -Name "fDenyTSConnections" -Value 1
  Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Remote Assistance" -Name "fAllowToGetHelp" -Value 0 -ErrorAction SilentlyContinue

  Disable-PSRemoting -Force -ErrorAction SilentlyContinue
  Stop-Service -Name WinRM -Force -ErrorAction SilentlyContinue
  Set-Service -Name WinRM -StartupType Disabled -ErrorAction SilentlyContinue
  Stop-Service -Name RemoteRegistry -Force -ErrorAction SilentlyContinue
  Set-Service -Name RemoteRegistry -StartupType Disabled -ErrorAction SilentlyContinue

  Disable-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue
  Disable-NetFirewallRule -DisplayGroup "Windows Remote Management" -ErrorAction SilentlyContinue
  Disable-NetFirewallRule -DisplayGroup "Remote Assistance" -ErrorAction SilentlyContinue
  Disable-NetFirewallRule -DisplayGroup "File and Printer Sharing" -ErrorAction SilentlyContinue
  Disable-NetFirewallRule -DisplayGroup "Network Discovery" -ErrorAction SilentlyContinue

  Get-NetFirewallRule -Direction Inbound -ErrorAction SilentlyContinue |
    Where-Object {
      $_.DisplayName -match "Uzak|Remote|WinRM|MasaÃ¼stÃ¼|YardÄ±m|SMB|RPC|WMI|YazKlinik|Orthanc|DICOM|Tailscale|5052|5443|3389|5985|445|135"
    } |
    Set-NetFirewallRule -Enabled False -ErrorAction SilentlyContinue

  Write-Host "Portproxy sabitleniyor: 0.0.0.0:$PublicPort -> 127.0.0.1:$InternalPort"
  Set-Service -Name iphlpsvc -StartupType Automatic -ErrorAction SilentlyContinue
  Start-Service -Name iphlpsvc -ErrorAction SilentlyContinue
  netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$PublicPort | Out-Null
  netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$PublicPort connectaddress=127.0.0.1 connectport=$InternalPort | Out-Host

  Write-Host "Sadece TCP $PublicPort inbound izin kurali yenileniyor..."
  Get-NetFirewallRule -DisplayName "YazKlinik D700 ONLY $PublicPort TCP Inbound" -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule -ErrorAction SilentlyContinue

  New-NetFirewallRule `
    -DisplayName "YazKlinik D700 ONLY $PublicPort TCP Inbound" `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $PublicPort `
    -Profile Any `
    -EdgeTraversalPolicy Block `
    -Description "D700 lockdown: dis erisim icin tek izinli inbound TCP portu." | Out-Host

  Write-Host "Son durum kaydediliyor..."
  Get-NetFirewallProfile |
    Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction, LogBlocked, LogFileName |
    Format-Table -AutoSize

  Get-NetFirewallRule -Enabled True -Direction Inbound -Action Allow |
    Select-Object DisplayName, Profile, Direction, Action |
    Format-Table -AutoSize

  netsh interface portproxy show all | Out-Host
  Get-NetTCPConnection -State Listen |
    Where-Object { $_.LocalPort -in @($PublicPort, $InternalPort, 3389, 5985, 445, 135, 5052, 8042, 4242) } |
    Sort-Object LocalPort |
    Select-Object LocalAddress, LocalPort, OwningProcess |
    Format-Table -AutoSize

  "OK $(Get-Date -Format s) - Only inbound TCP $PublicPort is allowed by Windows Firewall." |
    Set-Content -Path (Join-Path $BackupDir "LOCKDOWN_OK.txt") -Encoding UTF8

  Write-Host "TAMAM: Windows Firewall acik, inbound varsayilan BLOCK, sadece TCP $PublicPort izinli." -ForegroundColor Green
  Write-Host "Geri almak gerekirse: SECURITY_ROLLBACK_FIREWALL_ADMIN.bat dosyasini yonetici calistirin." -ForegroundColor Yellow
}
finally {
  Stop-Transcript | Out-Null
}

