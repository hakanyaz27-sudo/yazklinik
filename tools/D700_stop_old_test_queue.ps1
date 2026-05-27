param(
  [int]$Seconds = 90,
  [string]$LogPath = "D:\YazKlinik_Final_D700\runtime_state\maintenance_logs\old_test_queue_guard.log",
  [switch]$KillQuickCheck,
  [int]$MinAgeSeconds = 120,
  [switch]$EnableImmediateRiskKill
)

$ErrorActionPreference = "SilentlyContinue"
$Seconds = [int][Math]::Min(180, [Math]::Max(1, $Seconds))
$MinAgeSeconds = [int][Math]::Min(3600, [Math]::Max(0, $MinAgeSeconds))

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogPath) | Out-Null

function Test-HeavyCommandLine {
  param([string]$CommandLine)
  if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $false }
  $cmd = $CommandLine
  if ($cmd -like "*Stop-OldChildren*") { return $true }
  if ($cmd -like "*D700_FORCE_START*") { return $true }
  if ($cmd -like "*YAZKLINIK_FORCE_RESTART=1*" -and $cmd -like "*D700_BASLAT.bat*") { return $true }
  if ($cmd -like "*D700_web_recover_once.ps1*") { return $true }
  if ($cmd -like "*D700_stop_old_test_queue.ps1*") { return $true }
  $looksLikePythonRun = (
    $cmd -like "*python.exe*" -or
    $cmd -like "*pythonw.exe*" -or
    $cmd -like "*.venv*Scripts*python*" -or
    $cmd -like "* py *" -or
    $cmd -like "* pip *"
  )
  if (-not $looksLikePythonRun) { return $false }
  if ($cmd -like "*-m py_compile*" -or $cmd -like "*py_compile.compile*") { return $true }
  if ($cmd -like "*wheelhouse-download*") { return $true }
  if ($cmd -like "*pip download*" -or $cmd -like "*-m pip download*") { return $true }
  if ($cmd -like "*D700_PERF_AUDIT.py*") { return $true }
  if ($KillQuickCheck -or (($env:YAZKLINIK_GUARD_KILL_QUICKCHECK + "") -eq "1")) {
    if ($cmd -like "*CODEX_QUICK_CHECK.py*") { return $true }
  }
  return $false
}

function Test-ImmediateRiskCommandLine {
  param([string]$CommandLine)
  $allowImmediate = $EnableImmediateRiskKill -or ((($env:YAZKLINIK_GUARD_ENABLE_IMMEDIATE_RISK + "") -eq "1"))
  if (-not $allowImmediate) { return $false }
  if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $false }
  $cmd = $CommandLine
  if ($cmd -like "*Stop-OldChildren*") { return $true }
  if ($cmd -like "*D700_FORCE_START*") { return $true }
  if ($cmd -like "*YAZKLINIK_FORCE_RESTART=1*" -and $cmd -like "*D700_BASLAT.bat*") { return $true }
  return $false
}

function Stop-ProcessTreeSafe {
  param([int]$RootPid)
  if ($RootPid -le 0 -or $RootPid -eq $PID) { return }
  $children = @(Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $RootPid })
  foreach ($child in $children) {
    Stop-ProcessTreeSafe -RootPid ([int]$child.ProcessId)
  }
  Stop-Process -Id $RootPid -Force -ErrorAction SilentlyContinue
}

function Get-ProcessAgeSeconds {
  param([object]$Proc)
  try {
    $created = [datetime]$Proc.CreationDate
    return [int][Math]::Max(0, ((Get-Date) - $created).TotalSeconds)
  } catch {
    return 0
  }
}

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

$deadline = (Get-Date).AddSeconds([Math]::Max(1, $Seconds))
$seen = @{}
$killed = 0
$nextHeartbeat = (Get-Date).AddSeconds(10)
$protectedPids = Get-AncestorProcessIds

while ((Get-Date) -lt $deadline) {
  $targets = @(Get-CimInstance Win32_Process | Where-Object {
    if ($protectedPids.ContainsKey([int]$_.ProcessId)) { return $false }
    $isImmediateRisk = Test-ImmediateRiskCommandLine -CommandLine $_.CommandLine
    if (-not $isImmediateRisk -and -not (Test-HeavyCommandLine -CommandLine $_.CommandLine)) { return $false }
    $age = Get-ProcessAgeSeconds -Proc $_
    if ($isImmediateRisk) { return $true }
    return ($age -ge [Math]::Max(0, $MinAgeSeconds))
  })
  foreach ($target in $targets) {
    $key = [string]$target.ProcessId
    if (-not $seen.ContainsKey($key)) {
      $seen[$key] = $true
      $killed += 1
      Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value (
        (Get-Date).ToString("yyyy-MM-dd HH:mm:ss") +
        " KILL pid=$($target.ProcessId) ppid=$($target.ParentProcessId) age=$([int](Get-ProcessAgeSeconds -Proc $target))s name=$($target.Name) cmd=$($target.CommandLine)"
      )
    }
    Stop-ProcessTreeSafe -RootPid ([int]$target.ProcessId)
  }
  if ((Get-Date) -ge $nextHeartbeat) {
    Write-Host "OLD_TEST_QUEUE_GUARD_HEARTBEAT killed=$killed remaining_scan=$($targets.Count)"
    $nextHeartbeat = (Get-Date).AddSeconds(10)
  }
  Start-Sleep -Milliseconds 750
}

$remaining = @(Get-CimInstance Win32_Process | Where-Object {
  if ($protectedPids.ContainsKey([int]$_.ProcessId)) { return $false }
  if (-not (Test-HeavyCommandLine -CommandLine $_.CommandLine)) { return $false }
  $age = Get-ProcessAgeSeconds -Proc $_
  return ($age -ge [Math]::Max(0, $MinAgeSeconds))
})

Write-Host "OLD_TEST_QUEUE_GUARD_DONE killed=$killed remaining=$($remaining.Count) log=$LogPath"
if ($remaining.Count -gt 0) {
  $remaining | Select-Object ProcessId,ParentProcessId,Name,CommandLine | Format-Table -AutoSize
}
