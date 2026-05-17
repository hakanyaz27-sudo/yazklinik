param(
  [string]$Root = "D:\YazKlinik_Final_D300",
  [string]$BaseUrl = "https://127.0.0.1:5443"
)

$ErrorActionPreference = "Stop"

function Get-OrCreate-CronToken {
  param([string]$ConfigPath)
  $token = ""
  if (Test-Path -LiteralPath $ConfigPath) {
    $line = Get-Content -LiteralPath $ConfigPath |
      Where-Object { $_ -match '^\s*YAZKLINIK_CRON_TOKEN\s*=' } |
      Select-Object -First 1
    if ($line) {
      $token = ($line -replace '^\s*YAZKLINIK_CRON_TOKEN\s*=', '').Trim()
    }
  }
  if (-not $token) {
    $token = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    Add-Content -LiteralPath $ConfigPath -Encoding UTF8 -Value ""
    Add-Content -LiteralPath $ConfigPath -Encoding UTF8 -Value "# Session 7 cron endpoint token"
    Add-Content -LiteralPath $ConfigPath -Encoding UTF8 -Value "YAZKLINIK_CRON_TOKEN=$token"
    Write-Host "YAZKLINIK_CRON_TOKEN config.env dosyasina eklendi. Server restart gerekir."
  }
  return $token
}

function Register-YazKlinikTask {
  param(
    [string]$Name,
    [Microsoft.Management.Infrastructure.CimInstance]$Trigger,
    [string]$CurlArgs
  )
  $action = New-ScheduledTaskAction -Execute "curl.exe" -Argument $CurlArgs
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
  Register-ScheduledTask -TaskName $Name -Action $action -Trigger $Trigger -Principal $principal -Settings $settings -Force | Out-Null
  Write-Host "OK: $Name"
}

$configPath = Join-Path $Root "config.env"
if (-not (Test-Path -LiteralPath $configPath)) {
  throw "config.env bulunamadi: $configPath"
}

$token = Get-OrCreate-CronToken -ConfigPath $configPath
$header = "X-Cron-Token: $token"
$jsonHeader = "Content-Type: application/json"

Register-YazKlinikTask `
  -Name "YazKlinik_MemnuniyetSurvey" `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 9:00am) `
  -CurlArgs "-k -s -X POST -H `"$header`" `"$BaseUrl/api/agents/memnuniyet/survey-yesterday`""

Register-YazKlinikTask `
  -Name "YazKlinik_BirthdayToday" `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 8:00am) `
  -CurlArgs "-k -s -X POST -H `"$header`" `"$BaseUrl/api/agents/memnuniyet/birthday-today`""

Register-YazKlinikTask `
  -Name "YazKlinik_PubMedCron" `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 7:00am) `
  -CurlArgs "-k -s -X POST -H `"$header`" -H `"$jsonHeader`" -d `"{\`"queries\`":[\`"preeclampsia\`",\`"gestational diabetes\`"],\`"max_per_query\`":3}`" `"$BaseUrl/api/agents/pubmed-cron/scan`""

$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours 1)
Register-YazKlinikTask `
  -Name "YazKlinik_StatusHourly" `
  -Trigger $hourly `
  -CurlArgs "-k -s `"$BaseUrl/api/status`""

Write-Host ""
Write-Host "Kurulum tamam. Ilk kez token eklendiyse D300_BASLAT.bat ile server'i restart edin."
Write-Host "Manuel test: Task Scheduler > Task Scheduler Library > YazKlinik_* > Run"
