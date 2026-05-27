$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $root 'D700_BASLAT.bat'
$logDir = Join-Path $root 'runtime_state\autostart'
$log = Join-Path $logDir 'D700_startup_helper.log'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
function Log([string]$m){$ts=Get-Date -Format 'yyyy-MM-dd HH:mm:ss'; Add-Content -LiteralPath $log -Encoding UTF8 -Value ("$ts $m")}
Log 'START helper invoked'
Start-Sleep -Seconds 20
$launchLock = Join-Path $env:TEMP 'YazKlinik_D700_BASLAT.lock'
$runner = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
  $_.Name -match '^pythonw?\.exe$' -and
  $_.CommandLine -and
  $_.CommandLine.Contains($root) -and
  $_.CommandLine.Contains('D700_SERVICE_RUNNER.py')
}
if ($runner) {
  Log ('SKIP service runner already active count=' + @($runner).Count)
  exit 0
}
if (Test-Path -LiteralPath $launchLock) {
  Log ('SKIP launch lock present: ' + $launchLock)
  exit 0
}
$listen = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 5443 } | Select-Object -First 1
if ($listen) { Log ('SKIP already listening pid=' + $listen.OwningProcess); exit 0 }
if (-not (Test-Path -LiteralPath $launcher)) { Log ('ERROR launcher missing: ' + $launcher); exit 1 }
Log ('LAUNCH ' + $launcher)
Start-Process -FilePath $launcher -WorkingDirectory $root -WindowStyle Minimized
$ok=$false
for($i=0;$i -lt 60;$i++){
  Start-Sleep -Seconds 5
  $listen = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 5443 } | Select-Object -First 1
  if($listen){ Log ('READY pid=' + $listen.OwningProcess + ' after=' + (($i+1)*5) + 's'); $ok=$true; break }
}
if(-not $ok){ Log 'TIMEOUT no 5443 listener after 300s' }
exit 0





