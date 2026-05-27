$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $Root "runtime_state\caddy"
$PidFile = Join-Path $RuntimeDir "caddy.pid"
$Caddyfile = Join-Path $Root "infra\caddy\Caddyfile"

Write-Host ""
Write-Host "=== D700 Caddy Accel Durdur ==="

# Native caddy (pidfile) varsa kapat.
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

Write-Host "CADDY_ACCEL_STOP_OK"
