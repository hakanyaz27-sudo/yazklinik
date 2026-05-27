[CmdletBinding()]
param(
    [string]$ProjectRoot = "D:\YazKlinik_Final_D700",
    [string]$DriveRoot = "J:\"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Get-DirSizeGb {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return 0.0 }
    $sum = (Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    return [math]::Round(($sum / 1GB), 3)
}

function Get-OllamaModelNames {
    $names = @()
    try {
        $raw = & ollama list 2>$null
        if ($raw) {
            $rows = @($raw | Select-Object -Skip 1)
            foreach ($r in $rows) {
                $line = ("" + $r).Trim()
                if (-not $line) { continue }
                $name = ($line -split "\s+")[0].Trim()
                if ($name) { $names += $name }
            }
        }
    } catch {}
    return @($names | Sort-Object -Unique)
}

if (-not (Test-Path -LiteralPath $ProjectRoot)) {
    throw "ProjectRoot yok: $ProjectRoot"
}
if (-not (Test-Path -LiteralPath $DriveRoot)) {
    throw "DriveRoot yok: $DriveRoot"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$coreRoot = Join-Path $DriveRoot ("YazKlinik_D700_CORE_SETUP_" + $stamp)
$ollamaPackRoot = Join-Path $DriveRoot ("YazKlinik_D700_OLLAMA_MODELS_PACK_" + $stamp)

Write-Host ""
Write-Host "[1/7] Core paket hazirlaniyor..." -ForegroundColor Cyan
Ensure-Directory -Path $coreRoot
$coreApp = Join-Path $coreRoot "APP_SOURCE"
Ensure-Directory -Path $coreApp

Write-Host "[2/7] Core APP_SOURCE kopyalaniyor..." -ForegroundColor Cyan
$excludeDirs = @(
    (Join-Path $ProjectRoot ".venv"),
    (Join-Path $ProjectRoot "__pycache__"),
    (Join-Path $ProjectRoot "MEDGEMMA_OLLAMA_PACK"),
    (Join-Path $ProjectRoot "runtime_state"),
    (Join-Path $ProjectRoot "models\huggingface\hub\models--google--medgemma-1.5-4b-it"),
    (Join-Path $ProjectRoot "models\huggingface\hub\models--google--medgemma-4b-it"),
    (Join-Path $ProjectRoot "models\huggingface\hub\models--google--medgemma-4b-pt"),
    (Join-Path $ProjectRoot "models\huggingface\hub\models--google--medgemma-27b-text-it"),
    (Join-Path $ProjectRoot "models\huggingface\hub\models--google--medgemma-27b-it")
)

$coreArgs = @(
    $ProjectRoot,
    $coreApp,
    "/E",
    "/R:1",
    "/W:1",
    "/NFL",
    "/NDL",
    "/NP",
    "/NJH",
    "/NJS",
    "/XD"
) + $excludeDirs + @(
    "/XF",
    "*.log",
    "*.err.log"
)
& robocopy @coreArgs | Out-Null
if ($LASTEXITCODE -ge 8) {
    throw "Core kopyalama hatasi (robocopy code=$LASTEXITCODE)"
}

$ollamaModels = Get-OllamaModelNames
$listFileCore = Join-Path $coreRoot "OLLAMA_MODEL_LIST.txt"
if ($ollamaModels.Count -eq 0) {
    Set-Content -LiteralPath $listFileCore -Value "medgemma:27b" -Encoding ASCII
} else {
    $ollamaModels | Set-Content -LiteralPath $listFileCore -Encoding ASCII
}

$pullPs1 = @"
param(
  [string]`$ModelListPath = "`$PSScriptRoot\OLLAMA_MODEL_LIST.txt"
)
`$ErrorActionPreference = "Continue"

function Test-OllamaApi {
  try {
    `$r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
    return (`$r.StatusCode -ge 200 -and `$r.StatusCode -lt 300)
  } catch { return `$false }
}

function Get-OllamaExePath {
  `$cmd = Get-Command ollama.exe -ErrorAction SilentlyContinue
  if (`$cmd -and `$cmd.Source) { return `$cmd.Source }
  `$fallback = Join-Path `$env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
  if (Test-Path -LiteralPath `$fallback) { return `$fallback }
  return ""
}

`$exe = Get-OllamaExePath
if (-not `$exe) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install --id Ollama.Ollama -e --silent --accept-package-agreements --accept-source-agreements
    Start-Sleep -Seconds 3
    `$exe = Get-OllamaExePath
  }
}
if (-not `$exe) {
  Write-Host "[HATA] Ollama kurulamadi/bulunamadi." -ForegroundColor Red
  exit 1
}

if (-not (Test-OllamaApi)) {
  Start-Process -FilePath `$exe -ArgumentList "serve" -WindowStyle Hidden
  for (`$i=0; `$i -lt 40; `$i++) {
    if (Test-OllamaApi) { break }
    Start-Sleep -Seconds 1
  }
}
if (-not (Test-OllamaApi)) {
  Write-Host "[HATA] Ollama API acilamadi." -ForegroundColor Red
  exit 1
}

if (-not (Test-Path -LiteralPath `$ModelListPath)) {
  Write-Host "[HATA] Model listesi yok: `$ModelListPath" -ForegroundColor Red
  exit 1
}

`$models = Get-Content -LiteralPath `$ModelListPath -Encoding UTF8 | ForEach-Object { (`$_ + "").Trim() } | Where-Object { `$_ }
foreach (`$m in `$models) {
  Write-Host ("[PULL] " + `$m)
  ollama pull `$m
}
Write-Host "[OK] Model pull adimi tamamlandi." -ForegroundColor Green
"@
Set-Content -LiteralPath (Join-Path $coreRoot "OLLAMA_MODELLER_ONLINE_PULL.ps1") -Value $pullPs1 -Encoding ASCII

$coreLauncher = @"
@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title YazKlinik D700 Core Kurulum

set "TARGET=D:\YazKlinik_Final_D700"
echo.
echo ============================================================
echo  YazKlinik D700 CORE kurulum
echo  Kaynak: %~dp0APP_SOURCE
echo  Hedef : %TARGET%
echo ============================================================
echo.
pause

robocopy "%~dp0APP_SOURCE" "%TARGET%" /E /R:1 /W:1 /NFL /NDL /NP /NJH /NJS
if errorlevel 8 (
  echo [HATA] Core dosya kopyalama basarisiz.
  pause
  exit /b 1
)

echo.
echo Ollama model kurulumu:
echo   1^) Online tum listedeki modelleri indir (medgemma dahil)
echo   2^) Simdilik atla
set /p _m=Secim [1/2]:
if "%_m%"=="1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0OLLAMA_MODELLER_ONLINE_PULL.ps1"
)

echo.
call "%TARGET%\D700_ILK_KURULUM.bat"
endlocal
"@
Set-Content -LiteralPath (Join-Path $coreRoot "KURULUM_CORE_BASLAT.bat") -Value $coreLauncher -Encoding ASCII

Set-Content -LiteralPath (Join-Path $coreRoot "KURULUM_OKU_BENI.txt") -Value @"
YAZKLINIK D700 CORE PAKET

1) Yeni PC'de: KURULUM_CORE_BASLAT.bat
2) Online Ollama model indirmek isterseniz secim 1.
3) Offline model paketi ayri klasorde hazirlandi.
"@ -Encoding ASCII

Write-Host "[3/7] Ollama modeller pack hazirlaniyor..." -ForegroundColor Cyan
Ensure-Directory -Path $ollamaPackRoot
$runtimeOut = Join-Path $ollamaPackRoot "ollama-runtime"
$modelsOut = Join-Path $ollamaPackRoot "ollama-models"
Ensure-Directory -Path $runtimeOut
Ensure-Directory -Path $modelsOut

$runtimeSrc = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
$modelsSrc = Join-Path $env:USERPROFILE ".ollama\models"
if (-not (Test-Path -LiteralPath $runtimeSrc)) {
    throw "Ollama runtime bulunamadi: $runtimeSrc"
}
if (-not (Test-Path -LiteralPath $modelsSrc)) {
    throw "Ollama models bulunamadi: $modelsSrc"
}

Write-Host "[4/7] Ollama runtime kopyalaniyor..." -ForegroundColor Cyan
& robocopy $runtimeSrc $runtimeOut /E /R:1 /W:1 /NFL /NDL /NP /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) {
    throw "Ollama runtime kopyalama hatasi (robocopy code=$LASTEXITCODE)"
}

Write-Host "[5/7] Tum Ollama modelleri kopyalaniyor (medgemma dahil)..." -ForegroundColor Cyan
& robocopy $modelsSrc $modelsOut /E /R:1 /W:1 /NFL /NDL /NP /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) {
    throw "Ollama model kopyalama hatasi (robocopy code=$LASTEXITCODE)"
}

$ollamaInstaller = @"
@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title YazKlinik D700 Ollama Offline Pack Kurulum

set "RUNTIME_SRC=%~dp0ollama-runtime"
set "MODELS_SRC=%~dp0ollama-models"
set "RUNTIME_DST=%LocalAppData%\Programs\Ollama"
set "MODELS_DST=%USERPROFILE%\.ollama\models"

echo.
echo ============================================================
echo  YazKlinik D700 OLLAMA OFFLINE PAKET KURULUM
echo ============================================================
echo.
pause

if not exist "%RUNTIME_SRC%\ollama.exe" (
  echo [HATA] ollama-runtime eksik.
  pause
  exit /b 1
)
if not exist "%MODELS_SRC%\manifests" (
  echo [HATA] ollama-models eksik.
  pause
  exit /b 1
)

robocopy "%RUNTIME_SRC%" "%RUNTIME_DST%" /E /R:1 /W:1 /NFL /NDL /NP /NJH /NJS
if errorlevel 8 (
  echo [HATA] Runtime kopyalama basarisiz.
  pause
  exit /b 1
)

robocopy "%MODELS_SRC%" "%MODELS_DST%" /E /R:1 /W:1 /NFL /NDL /NP /NJH /NJS
if errorlevel 8 (
  echo [HATA] Model kopyalama basarisiz.
  pause
  exit /b 1
)

start "" "%RUNTIME_DST%\ollama.exe" serve
timeout /t 5 /nobreak >nul
ollama list
echo.
echo [OK] Offline Ollama model kurulumu tamamlandi.
pause
endlocal
"@
Set-Content -LiteralPath (Join-Path $ollamaPackRoot "KURULUM_OLLAMA_OFFLINE_PAKET.bat") -Value $ollamaInstaller -Encoding ASCII
Set-Content -LiteralPath (Join-Path $ollamaPackRoot "OLLAMA_MODEL_LIST.txt") -Value (($ollamaModels -join [Environment]::NewLine)) -Encoding ASCII

Write-Host "[6/7] Raporlar yaziliyor..." -ForegroundColor Cyan
$coreReport = [pscustomobject]@{
    package = "core"
    root = $coreRoot
    app_source_gb = Get-DirSizeGb -Path $coreApp
    ollama_model_count_in_list = $ollamaModels.Count
    created_at = (Get-Date).ToString("s")
}
$coreReport | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $coreRoot "CORE_REPORT.json") -Encoding UTF8

$ollamaReport = [pscustomobject]@{
    package = "ollama_models"
    root = $ollamaPackRoot
    runtime_gb = Get-DirSizeGb -Path $runtimeOut
    ollama_models_gb = Get-DirSizeGb -Path $modelsOut
    total_gb = Get-DirSizeGb -Path $ollamaPackRoot
    model_count = $ollamaModels.Count
    created_at = (Get-Date).ToString("s")
}
$ollamaReport | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $ollamaPackRoot "OLLAMA_PACK_REPORT.json") -Encoding UTF8

$rootLauncher = @"
@echo off
call "%~dp0YazKlinik_D700_CORE_SETUP_$stamp\KURULUM_CORE_BASLAT.bat"
"@
Set-Content -LiteralPath (Join-Path $DriveRoot "YazKlinik_D700_CORE_KUR_BASLAT.bat") -Value $rootLauncher -Encoding ASCII

Write-Host "[7/7] Tamamlandi." -ForegroundColor Green
Write-Host ("[OK] CORE: {0}" -f $coreRoot) -ForegroundColor Green
Write-Host ("[OK] OLLAMA PACK: {0}" -f $ollamaPackRoot) -ForegroundColor Green
