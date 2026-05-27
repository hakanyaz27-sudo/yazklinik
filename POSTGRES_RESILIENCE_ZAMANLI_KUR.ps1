param(
    [int]$IntervalMinutes = 30,
    [switch]$RunNow
)

$ErrorActionPreference = "Stop"
if ($IntervalMinutes -lt 5) { $IntervalMinutes = 5 }

$root = (Resolve-Path -LiteralPath (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$taskName = "YAZKLINIK_Postgres_Resilience_Check"
$logPath = Join-Path $root "runtime_state\postgres_resilience\scheduled_last.log"
New-Item -ItemType Directory -Path (Split-Path -Parent $logPath) -Force | Out-Null

$command = "cd /d `"$root`" && .\POSTGRES_RESILIENCE_CHECK.bat --with-admin --json > `"$logPath`" 2>&1"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $command"

$start = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $start `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

if ($RunNow) {
    Start-ScheduledTask -TaskName $taskName
}

Write-Host "TASK_OK name=$taskName interval_min=$IntervalMinutes run_now=$RunNow log=$logPath"
