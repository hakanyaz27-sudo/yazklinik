param(
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Load-ConfigEnv {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return }
  foreach ($raw in Get-Content -LiteralPath $Path -Encoding UTF8) {
    $line = ([string]$raw).Trim()
    if (-not $line) { continue }
    if ($line.StartsWith("#")) { continue }
    $eq = $line.IndexOf("=")
    if ($eq -lt 1) { continue }
    $key = $line.Substring(0, $eq).Trim()
    $val = $line.Substring($eq + 1).Trim()
    if (-not $key) { continue }
    [Environment]::SetEnvironmentVariable($key, $val, "Process")
  }
}

function Read-EnvValue {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Key
  )
  if (-not (Test-Path -LiteralPath $Path)) { return "" }
  foreach ($raw in Get-Content -LiteralPath $Path -Encoding UTF8) {
    $line = ([string]$raw).Trim()
    if (-not $line) { continue }
    if ($line.StartsWith("#")) { continue }
    $prefix = "$Key="
    if ($line.StartsWith($prefix)) {
      return $line.Substring($prefix.Length).Trim()
    }
  }
  return ""
}

function Stop-CeleryProcesses {
  $procs = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match "^pythonw?\.exe$" -and
    $_.CommandLine -and
    $_.CommandLine.Contains("yazklinik_celery_worker")
  }
  foreach ($p in $procs) {
    try {
      Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
      Write-Host ("  [OK] Eski Celery PID kapatildi: " + $p.ProcessId)
    } catch {
      Write-Host ("  [WARN] Celery PID kapatilamadi: " + $p.ProcessId)
    }
  }
}

Load-ConfigEnv -Path (Join-Path $Root "config.env")

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPy)) {
  throw "Python bulunamadi: $venvPy"
}

$redisUrl = $env:CELERY_BROKER
if (-not $redisUrl) { $redisUrl = $env:YAZKLINIK_REDIS_URL }
if (-not $redisUrl) { $redisUrl = $env:REDIS_URL }
if (-not $redisUrl) {
  $redisPassword = $env:REDIS_PASSWORD
  if (-not $redisPassword) {
    $redisPassword = Read-EnvValue -Path (Join-Path $Root "akillilik\.env") -Key "REDIS_PASSWORD"
  }
  if (-not $redisPassword) {
    $redisPassword = "CHANGE_yk_redis"
  }
  $redisUrl = "redis://:$redisPassword@localhost:16379/2"
}

$env:REDIS_URL = $redisUrl
$env:CELERY_BROKER = $redisUrl
$env:CELERY_RESULT = $redisUrl

Write-Host ""
Write-Host "=== D700 Celery Baslat ==="
Write-Host ("Root      : " + $Root)
Write-Host ("Redis     : " + $redisUrl)
Write-Host ("Python    : " + $venvPy)
Write-Host ""

if (-not $SkipInstall) {
  Write-Host "[1/4] celery[redis] kontrol/kurulum..."
  & $venvPy -m pip install "celery[redis]" --disable-pip-version-check
  if ($LASTEXITCODE -ne 0) {
    throw "pip install celery[redis] basarisiz."
  }
} else {
  Write-Host "[1/4] Paket kurulumu atlandi (--SkipInstall)."
}

Write-Host "[2/4] Eski Celery surecleri temizleniyor..."
Stop-CeleryProcesses

$runDir = Join-Path $Root "runtime_state\celery"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$workerOut = Join-Path $runDir "celery_worker.log"
$workerErr = Join-Path $runDir "celery_worker.err.log"
$beatOut = Join-Path $runDir "celery_beat.log"
$beatErr = Join-Path $runDir "celery_beat.err.log"
$beatState = Join-Path $runDir "celerybeat-schedule"
$beatPid = Join-Path $runDir "celerybeat.pid"
if (Test-Path -LiteralPath $beatPid) {
  Remove-Item -LiteralPath $beatPid -Force -ErrorAction SilentlyContinue
}

Write-Host "[3/4] Celery worker baslatiliyor..."
$workerArgs = @(
  "-m", "celery",
  "-A", "yazklinik_celery_worker",
  "worker",
  "--pool=solo",
  "--loglevel=INFO",
  "--hostname=d700_worker@%h"
)
$workerProc = Start-Process -FilePath $venvPy `
  -ArgumentList $workerArgs `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -RedirectStandardOutput $workerOut `
  -RedirectStandardError $workerErr `
  -PassThru

Write-Host "[4/4] Celery beat baslatiliyor..."
$beatArgs = @(
  "-m", "celery",
  "-A", "yazklinik_celery_worker",
  "beat",
  "--loglevel=INFO",
  "--schedule=$beatState",
  "--pidfile=$beatPid"
)
$beatProc = Start-Process -FilePath $venvPy `
  -ArgumentList $beatArgs `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -RedirectStandardOutput $beatOut `
  -RedirectStandardError $beatErr `
  -PassThru

Start-Sleep -Seconds 4

$aliveWorker = Get-Process -Id $workerProc.Id -ErrorAction SilentlyContinue
$aliveBeat = Get-Process -Id $beatProc.Id -ErrorAction SilentlyContinue

if (-not $aliveWorker -or -not $aliveBeat) {
  throw "Celery worker/beat sureclerinden biri ayakta degil. Loglar: $runDir"
}

Write-Host ""
Write-Host "CELERY_OK"
Write-Host ("  Worker PID : " + $workerProc.Id)
Write-Host ("  Beat PID   : " + $beatProc.Id)
Write-Host ("  Log klasor : " + $runDir)
