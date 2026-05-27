param(
  [int]$IntervalMinutes = 60,
  [string]$TaskName = "YazKlinik_D500_Postgres_Shadow_Sync",
  [switch]$RunNow,
  [switch]$Remove,
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Worker = Join-Path $Root "POSTGRES_SHADOW_SYNC_WORKER.bat"

if (-not (Test-Path -LiteralPath $Worker)) {
  throw "Worker BAT bulunamadi: $Worker"
}

if ($IntervalMinutes -lt 15) {
  throw "Guvenlik icin IntervalMinutes en az 15 olmali."
}

if ($Remove) {
  if ($WhatIf) {
    Write-Host "WHATIF remove scheduled task: $TaskName"
    exit 0
  }
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "OK removed scheduled task: $TaskName"
  exit 0
}

$Action = New-ScheduledTaskAction `
  -Execute "cmd.exe" `
  -Argument "/c `"$Worker`"" `
  -WorkingDirectory $Root

$Trigger = New-ScheduledTaskTrigger -Once `
  -At (Get-Date).AddMinutes(1) `
  -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
  -RepetitionDuration (New-TimeSpan -Days 3650)

$Settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew

if ($WhatIf) {
  Write-Host "WHATIF create/update scheduled task: $TaskName every $IntervalMinutes minutes"
  Write-Host "Worker: $Worker"
  exit 0
}

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $Action `
  -Trigger $Trigger `
  -Settings $Settings `
  -Description "YazKlinik D700 PostgreSQL shadow mirror sync" `
  -Force | Out-Null

Write-Host "OK scheduled task ready: $TaskName every $IntervalMinutes minutes"

if ($RunNow) {
  Start-ScheduledTask -TaskName $TaskName
  Write-Host "OK scheduled task started once now."
}

