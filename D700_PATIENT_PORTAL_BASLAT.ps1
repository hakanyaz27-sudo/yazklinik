param(
  [switch]$Silent
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $Root "config.env"
$Pythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Runner = Join-Path $Root "D700_SERVICE_RUNNER.py"
$Script = Join-Path $Root "yazklinik_patient_portal_public.py"
$OutLog = Join-Path $Root "D700_patient_portal.log"
$ErrLog = Join-Path $Root "D700_patient_portal.err.log"

if (Test-Path -LiteralPath $ConfigPath) {
  Get-Content -LiteralPath $ConfigPath -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or $line -notmatch "=") { return }
    $k, $v = $line.Split("=", 2)
    if ($k) { [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), "Process") }
  }
}

if (-not $env:YAZKLINIK_PATIENT_PORTAL_PORT) { $env:YAZKLINIK_PATIENT_PORTAL_PORT = "5053" }
if (-not $env:YAZKLINIK_PATIENT_PORTAL_HOST) { $env:YAZKLINIK_PATIENT_PORTAL_HOST = "127.0.0.1" }
if (-not $env:YAZKLINIK_PATIENT_PORTAL_BASE_URL) { $env:YAZKLINIK_PATIENT_PORTAL_BASE_URL = "https://hasta.yazhakan.com.tr" }

$Port = [int]$env:YAZKLINIK_PATIENT_PORTAL_PORT
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
  Select-Object -First 1 -ExpandProperty OwningProcess
if ($existing) {
  try {
    Stop-Process -Id $existing -Force -ErrorAction Stop
    Start-Sleep -Seconds 1
    if (-not $Silent) { Write-Host "[patient-portal] eski PID $existing durduruldu" }
  } catch {
    throw "[patient-portal] port $Port uzerindeki PID $existing kapatilamadi: $($_.Exception.Message)"
  }
}

if (-not (Test-Path -LiteralPath $Pythonw)) { $Pythonw = $Python }
if (-not (Test-Path -LiteralPath $Pythonw)) { throw ".venv Python bulunamadi: $Pythonw" }
if (-not (Test-Path -LiteralPath $Runner)) { throw "Runner bulunamadi: $Runner" }
if (-not (Test-Path -LiteralPath $Script)) { throw "Portal script bulunamadi: $Script" }

$proc = Start-Process -FilePath $Pythonw `
  -ArgumentList @($Runner, $Script, $OutLog, $ErrLog) `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -PassThru

Start-Sleep -Seconds 3
$ok = $false
try {
  $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/healthz" -UseBasicParsing -TimeoutSec 8
  $ok = ($resp.StatusCode -eq 200)
} catch {
  $ok = $false
}

if (-not $ok) {
  $tail = ""
  if (Test-Path -LiteralPath $ErrLog) {
    $tail = (Get-Content -LiteralPath $ErrLog -Tail 20 -ErrorAction SilentlyContinue) -join "`n"
  }
  throw "[patient-portal] basladi ama healthz cevap vermedi. PID=$($proc.Id) $tail"
}

if (-not $Silent) {
  Write-Host "[patient-portal] OK PID=$($proc.Id) http://127.0.0.1:$Port/healthz"
}
