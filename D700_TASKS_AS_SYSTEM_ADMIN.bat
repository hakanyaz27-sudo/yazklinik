@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""D:\YazKlinik_Final_D700\D700_TASKS_AS_SYSTEM.ps1""';" ^
  "schtasks /query /tn D700-PG-DailyBackup /fo LIST /v | Select-String -Pattern 'Run As User|Logon Mode|Last Result';" ^
  "schtasks /query /tn D700-PG-MonthlyRestoreSmoke /fo LIST /v | Select-String -Pattern 'Run As User|Logon Mode|Last Result';" ^
  "schtasks /query /tn D700-WeeklyQuickCheck /fo LIST /v | Select-String -Pattern 'Run As User|Logon Mode|Last Result'"
endlocal
