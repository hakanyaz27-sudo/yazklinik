$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host ""
Write-Host "=== D700 Celery Durdur ==="

$procs = Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match "^pythonw?\.exe$" -and
  $_.CommandLine -and
  $_.CommandLine.Contains("yazklinik_celery_worker")
}

if (-not $procs) {
  Write-Host "  Celery sureci bulunamadi."
  exit 0
}

foreach ($p in $procs) {
  try {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
    Write-Host ("  [OK] PID kapatildi: " + $p.ProcessId)
  } catch {
    Write-Host ("  [WARN] PID kapatilamadi: " + $p.ProcessId)
  }
}

$beatPid = Join-Path $Root "runtime_state\celery\celerybeat.pid"
if (Test-Path -LiteralPath $beatPid) {
  Remove-Item -LiteralPath $beatPid -Force -ErrorAction SilentlyContinue
}

Write-Host "CELERY_STOP_OK"
