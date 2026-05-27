param(
  [int]$WaitSeconds = 300,
  [int]$CooldownSeconds = 180
)

$ErrorActionPreference = "SilentlyContinue"
$Root = "D:\YazKlinik_Final_D700"
$StateDir = Join-Path $Root "runtime_state\maintenance_locks"
$RecoverLockDir = Join-Path $StateDir "web_recover_once.lockdir"
$RecoverPidFile = Join-Path $RecoverLockDir "pid.txt"
$RecoverStampFile = Join-Path $StateDir "web_recover_once.last"

function Get-AncestorProcessIds {
  $ids = @{}
  $current = Get-CimInstance Win32_Process -Filter "ProcessId=$PID" -ErrorAction SilentlyContinue
  while ($current) {
    $ids[[int]$current.ProcessId] = $true
    $parentId = [int]$current.ParentProcessId
    if ($parentId -le 0 -or $ids.ContainsKey($parentId)) { break }
    $current = Get-CimInstance Win32_Process -Filter "ProcessId=$parentId" -ErrorAction SilentlyContinue
  }
  return $ids
}

function Stop-ProcessTreeSafe {
  param(
    [int]$RootPid,
    [hashtable]$ProtectedPids
  )
  if ($RootPid -le 0 -or $ProtectedPids.ContainsKey($RootPid)) { return }
  $children = @(Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $RootPid })
  foreach ($child in $children) {
    Stop-ProcessTreeSafe -RootPid ([int]$child.ProcessId) -ProtectedPids $ProtectedPids
  }
  Stop-Process -Id $RootPid -Force -ErrorAction SilentlyContinue
}

function Test-WebProcessCommand {
  param([string]$CommandLine)
  if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $false }
  if (-not $CommandLine.Contains($Root)) { return $false }
  if ($CommandLine.Contains("CODEX_WAIT_WEB_READY.py")) { return $true }
  if ($CommandLine.Contains("yazklinik_web.py")) { return $true }
  return $false
}

function Test-Url {
  param([string]$Url)
  try {
    return (& curl.exe -k --connect-timeout 1 --max-time 3 -s -o NUL -w "%{http_code} %{time_total}" $Url)
  } catch {
    return "000 0"
  }
}

function Test-WebHealthyTwice {
  $streak = 0
  for ($i = 0; $i -lt 2; $i++) {
    $http = Test-Url "http://127.0.0.1:5052/giris"
    $https = Test-Url "https://127.0.0.1:5443/giris"
    if ($http.StartsWith("200 ") -and $https.StartsWith("200 ")) {
      $streak += 1
    } else {
      $streak = 0
    }
    if ($streak -ge 2) {
      return $true
    }
    if ($i -lt 1) {
      Start-Sleep -Seconds 2
    }
  }
  return $false
}

function Read-LockPid {
  if (-not (Test-Path -LiteralPath $RecoverPidFile)) {
    return 0
  }
  try {
    $pidText = (Get-Content -LiteralPath $RecoverPidFile -Raw).Trim()
    $pidValue = 0
    [int]::TryParse($pidText, [ref]$pidValue) | Out-Null
    return $pidValue
  } catch {
    return 0
  }
}

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

if (Test-Path -LiteralPath $RecoverLockDir) {
  $lockPid = Read-LockPid
  $lockProc = $null
  if ($lockPid -gt 0) {
    $lockProc = Get-Process -Id $lockPid -ErrorAction SilentlyContinue
  }
  if ($lockProc -and $lockPid -ne $PID) {
    Write-Host ("WEB_RECOVER_SKIP_ACTIVE pid={0}" -f $lockPid)
    exit 0
  }
  Remove-Item -LiteralPath $RecoverLockDir -Recurse -Force -ErrorAction SilentlyContinue
}

try {
  New-Item -ItemType Directory -Path $RecoverLockDir -ErrorAction Stop | Out-Null
} catch {
  Write-Host "WEB_RECOVER_SKIP_LOCK_BUSY"
  exit 0
}

$global:LASTEXITCODE = 0
$exitCode = 1
try {
  Set-Content -LiteralPath $RecoverPidFile -Value ([string]$PID) -Encoding ASCII

  if (Test-WebHealthyTwice) {
    Set-Content -LiteralPath $RecoverStampFile -Value ((Get-Date).ToString("s")) -Encoding ASCII
    Write-Host "WEB_RECOVER_SKIP_ALREADY_HEALTHY"
    $exitCode = 0
  } else {
    if ($CooldownSeconds -gt 0 -and (Test-Path -LiteralPath $RecoverStampFile)) {
      try {
        $ageSec = [int][Math]::Max(0, ((Get-Date) - (Get-Item -LiteralPath $RecoverStampFile).LastWriteTime).TotalSeconds)
      } catch {
        $ageSec = $CooldownSeconds
      }
      if ($ageSec -lt $CooldownSeconds -and (Test-WebHealthyTwice)) {
        Write-Host ("WEB_RECOVER_SKIP_COOLDOWN age={0}s" -f $ageSec)
        $exitCode = 0
      }
    }

    if ($exitCode -ne 0) {
      $protected = Get-AncestorProcessIds
      $targets = @(Get-CimInstance Win32_Process | Where-Object {
        -not $protected.ContainsKey([int]$_.ProcessId) -and (Test-WebProcessCommand -CommandLine $_.CommandLine)
      })

      Write-Host "WEB_RECOVER_STOP_TARGETS count=$($targets.Count)"
      foreach ($target in ($targets | Sort-Object ProcessId -Descending)) {
        Write-Host "STOP pid=$($target.ProcessId) name=$($target.Name)"
        Stop-ProcessTreeSafe -RootPid ([int]$target.ProcessId) -ProtectedPids $protected
      }

      Start-Sleep -Seconds 2

      $lockDir = Join-Path $env:TEMP "YazKlinik\locks"
      $webLock = Join-Path $lockDir "web_5052.lock"
      if (Test-Path -LiteralPath $webLock) {
        Remove-Item -LiteralPath $webLock -Force -ErrorAction SilentlyContinue
        Write-Host "WEB_RECOVER_REMOVED_LOCK $webLock"
      } else {
        Write-Host "WEB_RECOVER_NO_LOCK"
      }

      $pythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"
      Start-Process -FilePath $pythonw -ArgumentList @(
        "D700_SERVICE_RUNNER.py",
        "yazklinik_web.py",
        "D700_server.log",
        "D700_server_HATA.log"
      ) -WorkingDirectory $Root -WindowStyle Hidden
      Write-Host "WEB_RECOVER_STARTED"

      $deadline = (Get-Date).AddSeconds([Math]::Max(1, $WaitSeconds))
      $streak = 0
      $tick = 0
      while ((Get-Date) -lt $deadline) {
        $tick += 1
        $conn = Get-NetTCPConnection -LocalPort 5052 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        $http = Test-Url "http://127.0.0.1:5052/giris"
        $https = Test-Url "https://127.0.0.1:5443/giris"
        if ($http.StartsWith("200 ") -and $https.StartsWith("200 ")) {
          $streak += 1
        } else {
          $streak = 0
        }
        Write-Host ("WEB_RECOVER_CHECK n={0} pid={1} http={2} https={3} streak={4}" -f $tick, $(if ($conn) { $conn.OwningProcess } else { "NO" }), $http, $https, $streak)
        if ($streak -ge 2) {
          Set-Content -LiteralPath $RecoverStampFile -Value ((Get-Date).ToString("s")) -Encoding ASCII
          Write-Host "WEB_RECOVER_OK"
          $exitCode = 0
          break
        }
        Start-Sleep -Seconds 8
      }
    }
  }
} finally {
  Remove-Item -LiteralPath $RecoverLockDir -Recurse -Force -ErrorAction SilentlyContinue
}

if ($exitCode -ne 0) {
  Write-Host "WEB_RECOVER_FAIL"
}
exit $exitCode
