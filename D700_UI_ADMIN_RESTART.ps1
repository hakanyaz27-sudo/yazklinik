$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$ports = @(5052, 5443)
$targets = New-Object System.Collections.Generic.HashSet[int]

foreach ($port in $ports) {
  $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
  foreach ($conn in $conns) {
    if ($conn.OwningProcess) {
      [void]$targets.Add([int]$conn.OwningProcess)
      $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)" -ErrorAction SilentlyContinue
      if ($proc -and $proc.ParentProcessId) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.ParentProcessId)" -ErrorAction SilentlyContinue
        if ($parent -and $parent.Name -match '^pythonw?\.exe$') {
          [void]$targets.Add([int]$parent.ProcessId)
        }
      }
    }
  }
}

foreach ($targetPid in ($targets | Sort-Object -Descending)) {
  try {
    Stop-Process -Id $targetPid -Force -ErrorAction Stop
    Write-Host "STOPPED PID=$targetPid"
  } catch {
    Write-Host "STOP_FAILED PID=$targetPid $($_.Exception.Message)"
  }
}

Start-Sleep -Seconds 3

$env:YAZKLINIK_KEEP_LAUNCHER_OPEN = "0"
$launcher = Join-Path $root "D700_BASLAT.bat"
Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "`"$launcher`"") -WorkingDirectory $root -WindowStyle Hidden

function Test-D700PingFast {
  param([int]$Port)
  try {
    $uri = "http://127.0.0.1:$Port/api/terminal/ping-fast"
    $resp = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 2
    if ($resp -and $resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
      return $true
    }
  } catch {}
  return $false
}

$newPid = $null
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Seconds 1
  foreach ($port in $ports) {
    $listen = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" } | Select-Object -First 1
    if ($listen -and $listen.OwningProcess) {
      $newPid = [int]$listen.OwningProcess
    }
  }
  if ($newPid -and ((Test-D700PingFast -Port 5052) -or (Test-D700PingFast -Port 5443))) {
    $ready = $true
    break
  }
}

if ($ready -and $newPid) {
  Write-Host "D700_UI_ADMIN_RESTART_DONE PID=$newPid READY=1"
} elseif ($newPid) {
  Write-Host "D700_UI_ADMIN_RESTART_DONE PID=$newPid READY=0"
} else {
  Write-Host "D700_UI_ADMIN_RESTART_DONE PID=UNKNOWN READY=0"
}

