$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).
  IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
  throw "Yonetici yetkisi gerekli. D700_TASKS_AS_SYSTEM_ADMIN.bat ile yukselterek calistirin."
}

$daily = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\YazKlinik_Final_D700\D700_PG_DAILY_BACKUP.ps1"'
$monthly = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\YazKlinik_Final_D700\D700_PG_MONTHLY_RESTORE_SMOKE.ps1"'
$weekly = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\YazKlinik_Final_D700\D700_WEEKLY_QUICK_CHECK.ps1"'

schtasks /create /tn D700-PG-DailyBackup /tr $daily /sc daily /st 02:30 /ru SYSTEM /rl HIGHEST /f | Out-Null
schtasks /create /tn D700-PG-MonthlyRestoreSmoke /tr $monthly /sc monthly /d 1 /st 03:30 /ru SYSTEM /rl HIGHEST /f | Out-Null
schtasks /create /tn D700-WeeklyQuickCheck /tr $weekly /sc weekly /d SUN /st 04:30 /ru SYSTEM /rl HIGHEST /f | Out-Null

schtasks /query /tn D700-PG-DailyBackup /fo LIST /v | Select-String -Pattern "Logon Mode|Run As User"
schtasks /query /tn D700-PG-MonthlyRestoreSmoke /fo LIST /v | Select-String -Pattern "Logon Mode|Run As User"
schtasks /query /tn D700-WeeklyQuickCheck /fo LIST /v | Select-String -Pattern "Logon Mode|Run As User"

Write-Host "TASK_SYSTEM_OK"
