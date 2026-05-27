param(
  [string]$PythonExe = "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe",
  [string]$QuickCheckScript = "D:\YazKlinik_Final_D700\CODEX_QUICK_CHECK.py",
  [string]$LogRoot = "D:\YazKlinik_Final_D700\runtime_state\maintenance_logs",
  [int]$RetentionDays = 60
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runLog = Join-Path $LogRoot ("weekly_quick_check_" + $stamp + ".log")
$lockFile = Join-Path $LogRoot "weekly_quick_check.lock"
$lockOwned = $false
$webPort = 5052

try {
  $cfgPath = Join-Path $PSScriptRoot "config.env"
  if (Test-Path -LiteralPath $cfgPath) {
    $rawPort = Get-Content -LiteralPath $cfgPath -Encoding UTF8 |
      Where-Object { $_ -match '^\s*YAZKLINIK_WEB_PORT\s*=' } |
      Select-Object -First 1
    if ($rawPort) {
      $parsed = (($rawPort -split "=", 2)[1]).Trim()
      $num = 0
      if ([int]::TryParse($parsed, [ref]$num) -and $num -gt 0) {
        $webPort = $num
      }
    }
  }
} catch {}

function Test-PidAlive {
  param([int]$ProcessId)
  if ($ProcessId -le 0) { return $false }
  try {
    Get-Process -Id $ProcessId -ErrorAction Stop | Out-Null
    return $true
  } catch {
    return $false
  }
}

function Wait-WebReady {
  param(
    [int]$Port = 5052,
    [int]$TimeoutSec = 300
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $code = & curl.exe --connect-timeout 1 --max-time 2 -s -o NUL -w "%{http_code}" ("http://127.0.0.1:{0}/giris" -f $Port) 2>$null
      if ("$code".Trim() -eq "200") { return $true }
    } catch {}
    Start-Sleep -Seconds 5
  }
  return $false
}

if (Test-Path -LiteralPath $lockFile) {
  $existingPid = 0
  try {
    $existingPid = [int](Get-Content -LiteralPath $lockFile -ErrorAction Stop |
      Select-Object -First 1).Trim()
  } catch {
    $existingPid = 0
  }
  if ((Test-PidAlive -ProcessId $existingPid)) {
    Write-Host "D700_WEEKLY_QUICK_CHECK_SKIP (zaten calisiyor, PID=$existingPid)"
    exit 0
  }
  Remove-Item -LiteralPath $lockFile -Force -ErrorAction SilentlyContinue
}

Set-Content -LiteralPath $lockFile -Value "$PID" -Encoding ASCII -Force
$lockOwned = $true
Start-Transcript -Path $runLog -Append | Out-Null

try {
  if (Wait-WebReady -Port $webPort -TimeoutSec 300) {
    Write-Host ("WEB_READY_OK port={0}" -f $webPort)
  } else {
    Write-Host ("WEB_READY_WARN port={0} timeout=300s (quick-check devam edecek)" -f $webPort)
  }

  if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python bulunamadi: $PythonExe"
  }
  if (-not (Test-Path -LiteralPath $QuickCheckScript)) {
    throw "Quick check script bulunamadi: $QuickCheckScript"
  }

  & $PythonExe $QuickCheckScript
  if ($LASTEXITCODE -ne 0) {
    throw "CODEX_QUICK_CHECK.py basarisiz. ExitCode=$LASTEXITCODE"
  }

  Get-ChildItem -Path $LogRoot -File -Filter "weekly_quick_check_*.log" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1 * $RetentionDays) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

  Write-Host "D700_WEEKLY_QUICK_CHECK_OK"
  Write-Host ("LOG_PATH=" + $runLog)
}
finally {
  if ($lockOwned) {
    try {
      Remove-Item -LiteralPath $lockFile -Force -ErrorAction SilentlyContinue
    } catch {}
  }
  Stop-Transcript | Out-Null
}
