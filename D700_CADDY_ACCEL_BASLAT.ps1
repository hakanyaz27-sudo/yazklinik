$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Caddyfile = Join-Path $Root "infra\caddy\Caddyfile"
$CertDir = Join-Path $Root "certs"
$CertCrt = Join-Path $CertDir "yazklinik_https.crt"
$CertKey = Join-Path $CertDir "yazklinik_https.key"
$RuntimeDir = Join-Path $Root "runtime_state\caddy"
$PidFile = Join-Path $RuntimeDir "caddy.pid"
$StdoutLog = Join-Path $RuntimeDir "caddy.stdout.log"
$StderrLog = Join-Path $RuntimeDir "caddy.stderr.log"
$WingetCaddy = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\CaddyServer.Caddy_Microsoft.Winget.Source_8wekyb3d8bbwe\caddy.exe"

if (-not (Test-Path -LiteralPath $Caddyfile)) {
  throw "Caddyfile bulunamadi: $Caddyfile"
}
if (-not (Test-Path -LiteralPath $CertCrt)) {
  throw "HTTPS sertifika bulunamadi: $CertCrt"
}
if (-not (Test-Path -LiteralPath $CertKey)) {
  throw "HTTPS key bulunamadi: $CertKey"
}

Write-Host ""
Write-Host "=== D700 Caddy Accel Baslat ==="
Write-Host ("Caddyfile: " + $Caddyfile)
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

# Varsa eski native Caddy prosesini sonlandir.
if (Test-Path -LiteralPath $PidFile) {
  try {
    $oldPid = [int](Get-Content -LiteralPath $PidFile -ErrorAction Stop | Select-Object -First 1)
    if ($oldPid -gt 0) {
      Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
    }
  } catch {}
  Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}
try {
  Get-CimInstance Win32_Process -Filter "Name='caddy.exe'" | Where-Object {
    $_.CommandLine -and $_.CommandLine.Contains($Caddyfile)
  } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
} catch {}

$caddyExe = $null
try {
  $cmd = Get-Command caddy -ErrorAction SilentlyContinue
  if ($cmd -and $cmd.Source) { $caddyExe = $cmd.Source }
} catch {}
if (-not $caddyExe -and (Test-Path -LiteralPath $WingetCaddy)) {
  $caddyExe = $WingetCaddy
}
if (-not $caddyExe) {
  throw "caddy.exe bulunamadi. once: winget install CaddyServer.Caddy"
}

$env:YAZKLINIK_CADDY_CERT = $CertCrt
$env:YAZKLINIK_CADDY_KEY = $CertKey

$proc = Start-Process `
  -FilePath $caddyExe `
  -ArgumentList @("run", "--config", $Caddyfile, "--adapter", "caddyfile", "--pidfile", $PidFile) `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -RedirectStandardOutput $StdoutLog `
  -RedirectStandardError $StderrLog `
  -PassThru

Start-Sleep -Seconds 3

$listen5443 = Get-NetTCPConnection -LocalPort 5443 -State Listen -ErrorAction SilentlyContinue
$listen5080 = Get-NetTCPConnection -LocalPort 5080 -State Listen -ErrorAction SilentlyContinue
if (-not $listen5443 -or -not $listen5080) {
  $errTail = ""
  if (Test-Path -LiteralPath $StderrLog) {
    $errTail = (Get-Content -LiteralPath $StderrLog -Tail 20 | Out-String)
  }
  throw ("Caddy ayaga kalkmadi. stderr: " + $errTail)
}

Write-Host ("ProcessId: " + $proc.Id)
Write-Host "Proxy URL : http://127.0.0.1:5080"
Write-Host "Proxy URL : https://127.0.0.1:5443"
