param(
  [string]$DailyTime = "02:30",
  [string]$MonthlyTime = "03:30",
  [string]$WeeklyDay = "SUN",
  [string]$WeeklyTime = "04:30"
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).
  IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
  throw "Yonetici yetkisi gerekli. Bu scripti Run as Administrator ile calistirin."
}

$dailyScript = "D:\YazKlinik_Final_D700\D700_PG_DAILY_BACKUP.ps1"
$monthlyScript = "D:\YazKlinik_Final_D700\D700_PG_MONTHLY_RESTORE_SMOKE.ps1"
$weeklyScript = "D:\YazKlinik_Final_D700\D700_WEEKLY_QUICK_CHECK.ps1"

if (-not (Test-Path $dailyScript)) { throw "Bulunamadi: $dailyScript" }
if (-not (Test-Path $monthlyScript)) { throw "Bulunamadi: $monthlyScript" }
if (-not (Test-Path $weeklyScript)) { throw "Bulunamadi: $weeklyScript" }

$dailyTask = "D700-PG-DailyBackup"
$monthlyTask = "D700-PG-MonthlyRestoreSmoke"
$weeklyTask = "D700-WeeklyQuickCheck"

$dailyCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$dailyScript`""
$monthlyCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$monthlyScript`""
$weeklyCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$weeklyScript`""

cmd /c "schtasks /query /tn `"$dailyTask`" >nul 2>nul"
if ($LASTEXITCODE -eq 0) {
  schtasks /delete /tn $dailyTask /f | Out-Null
}

cmd /c "schtasks /query /tn `"$monthlyTask`" >nul 2>nul"
if ($LASTEXITCODE -eq 0) {
  schtasks /delete /tn $monthlyTask /f | Out-Null
}
cmd /c "schtasks /query /tn `"$weeklyTask`" >nul 2>nul"
if ($LASTEXITCODE -eq 0) {
  schtasks /delete /tn $weeklyTask /f | Out-Null
}

cmd /c "schtasks /create /tn `"$dailyTask`" /tr `"$dailyCmd`" /sc daily /st $DailyTime /ru SYSTEM /rl HIGHEST /f >nul 2>nul"
$dailyCreateExit = $LASTEXITCODE
cmd /c "schtasks /create /tn `"$monthlyTask`" /tr `"$monthlyCmd`" /sc monthly /d 1 /st $MonthlyTime /ru SYSTEM /rl HIGHEST /f >nul 2>nul"
$monthlyCreateExit = $LASTEXITCODE
cmd /c "schtasks /create /tn `"$weeklyTask`" /tr `"$weeklyCmd`" /sc weekly /d $WeeklyDay /st $WeeklyTime /ru SYSTEM /rl HIGHEST /f >nul 2>nul"
$weeklyCreateExit = $LASTEXITCODE

if (($dailyCreateExit -ne 0) -or ($monthlyCreateExit -ne 0) -or ($weeklyCreateExit -ne 0)) {
  throw "SYSTEM task olusturma basarisiz. Bu scripti yonetici (Run as Administrator) ile calistirin. Interactive fallback kaldirildi."
}

Write-Host "TASKS_OK_SYSTEM"
