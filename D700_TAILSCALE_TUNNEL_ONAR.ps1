param(
    [switch]$AdminFix
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root "runtime_state\maintenance_logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogPath = Join-Path $LogDir "tailscale_tunnel_onar_$Stamp.log"

function Write-Step {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Write-Output $line
    Add-Content -Path $LogPath -Value $line -Encoding UTF8
}

function Find-Tailscale {
    $candidates = @(
        "C:\Program Files\Tailscale\tailscale.exe",
        "C:\Program Files (x86)\Tailscale\tailscale.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    $cmd = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    return $null
}

function Test-Url {
    param(
        [string]$Url,
        [switch]$Insecure
    )
    $args = @("-s", "-o", "NUL", "-w", "%{http_code} %{time_total}")
    if ($Insecure) {
        $args = @("-k") + $args
    }
    $args += $Url
    try {
        $result = & curl.exe @args
        Write-Step "$Url -> $result"
        return
    } catch {
        Write-Step "$Url -> ERROR $($_.Exception.Message)"
        return
    }
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Write-Step "D700 Tailscale tunnel onarimi basladi. Admin=$isAdmin AdminFix=$AdminFix"

$tailscale = Find-Tailscale
if (-not $tailscale) {
    Write-Step "HATA: tailscale.exe bulunamadi."
    exit 2
}
Write-Step "Tailscale CLI: $tailscale"

$svc = Get-Service -Name Tailscale -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-Step "HATA: Tailscale servisi bulunamadi."
    exit 3
}
Write-Step "Tailscale servis durumu: $($svc.Status), StartType=$($svc.StartType)"

if ($svc.Status -ne "Running") {
    Write-Step "Tailscale servisi baslatiliyor..."
    Start-Service -Name Tailscale -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}

if ($isAdmin) {
    try {
        Set-Service -Name Tailscale -StartupType Automatic
        Write-Step "Tailscale servisi Automatic yapildi."
    } catch {
        Write-Step "UYARI: Servis StartupType degistirilemedi: $($_.Exception.Message)"
    }
} else {
    Write-Step "UYARI: Admin degil; servis StartupType ve IP forwarding degisiklikleri atlandi."
}

Write-Step "Subnet route yeniden ilan ediliyor: 192.168.1.0/24"
& $tailscale set --unattended=true --auto-update=true --update-check=true --advertise-routes=192.168.1.0/24
Write-Step "tailscale set exit=$LASTEXITCODE"

if ($isAdmin -and $AdminFix) {
    Write-Step "AdminFix aktif: Windows IPv4 forwarding kalicilastiriliyor."
    $aliases = @("Ethernet 2", "Tailscale")
    foreach ($alias in $aliases) {
        try {
            Set-NetIPInterface -InterfaceAlias $alias -AddressFamily IPv4 -Forwarding Enabled -ErrorAction Stop
            Write-Step "$alias IPv4 Forwarding=Enabled"
        } catch {
            Write-Step "UYARI: $alias IPv4 forwarding ayarlanamadi: $($_.Exception.Message)"
        }
    }
    try {
        Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" -Name "IPEnableRouter" -Type DWord -Value 1
        Write-Step "Registry IPEnableRouter=1"
    } catch {
        Write-Step "UYARI: Registry IPEnableRouter yazilamadi: $($_.Exception.Message)"
    }
}

Write-Step "Tailscale durum okunuyor..."
$statusJson = & $tailscale status --json
$status = $statusJson | ConvertFrom-Json
$self = $status.Self
$routesOk = $false
if ($self.PrimaryRoutes -contains "192.168.1.0/24" -or $self.AllowedIPs -contains "192.168.1.0/24") {
    $routesOk = $true
}
Write-Step "Host=$($self.HostName) Online=$($self.Online) TailscaleIP=$($self.TailscaleIPs[0])"
Write-Step "AllowedIPs=$($self.AllowedIPs -join ',')"
Write-Step "PrimaryRoutes=$($self.PrimaryRoutes -join ',')"
Write-Step "KeyExpiry=$($self.KeyExpiry)"

Write-Step "D700 lokal/Tailscale HTTP smoke basliyor..."
Test-Url "http://127.0.0.1:5052/giris"
Test-Url "http://192.168.1.50:5052/giris"
if ($self.TailscaleIPs.Count -gt 0) {
    Test-Url ("http://{0}:5052/giris" -f $self.TailscaleIPs[0])
}
Test-Url "https://127.0.0.1:5443/giris" -Insecure
Test-Url "https://192.168.1.50:5443/giris" -Insecure
if ($self.TailscaleIPs.Count -gt 0) {
    Test-Url ("https://{0}:5443/giris" -f $self.TailscaleIPs[0]) -Insecure
}

if ($routesOk -and $self.Online) {
    Write-Step "TAILSCALE_TUNNEL_ONAR_OK"
    exit 0
}

Write-Step "TAILSCALE_TUNNEL_ONAR_UYARI: route veya online durum beklenen gibi degil."
exit 1
