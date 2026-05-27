[CmdletBinding()]
param(
    [string]$ProjectRoot = "D:\YazKlinik_Final_D700",
    [string]$OutputRoot = "",
    [string]$DriveRoot = "J:\",
    [switch]$IncludeOfflineAiPack = $true
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

if (-not (Test-Path -LiteralPath $ProjectRoot)) {
    throw "ProjectRoot bulunamadi: $ProjectRoot"
}
if (-not (Test-Path -LiteralPath $DriveRoot)) {
    throw "DriveRoot bulunamadi: $DriveRoot"
}

if (-not $OutputRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputRoot = Join-Path $DriveRoot ("YazKlinik_D700_WINDOWS_SETUP_" + $stamp)
}

Write-Host ""
Write-Host ("[1/6] Setup klasoru hazirlaniyor: {0}" -f $OutputRoot) -ForegroundColor Cyan
Ensure-Directory -Path $OutputRoot
$appOut = Join-Path $OutputRoot "APP_SOURCE"
Ensure-Directory -Path $appOut

Write-Host "[2/6] APP_SOURCE kopyalaniyor (core + wheelhouse, medgemma hf hariic)..." -ForegroundColor Cyan
$sourceMedgemmaHub = Join-Path $ProjectRoot "models\huggingface\hub"
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

$robocopyArgs = @(
    $ProjectRoot,
    $appOut,
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

& robocopy @robocopyArgs | Out-Null
if ($LASTEXITCODE -ge 8) {
    throw "APP_SOURCE kopyalama hatasi (robocopy code=$LASTEXITCODE)"
}

if ($IncludeOfflineAiPack) {
    Write-Host "[3/6] Offline AI pack kopyalaniyor..." -ForegroundColor Cyan
    $aiPackSrc = Join-Path $ProjectRoot "MEDGEMMA_OLLAMA_PACK"
    if (-not (Test-Path -LiteralPath $aiPackSrc)) {
        throw "MEDGEMMA_OLLAMA_PACK bulunamadi: $aiPackSrc"
    }
    $aiPackDest = Join-Path $OutputRoot "MEDGEMMA_OLLAMA_PACK"
    Ensure-Directory -Path $aiPackDest
    & robocopy $aiPackSrc $aiPackDest /E /R:1 /W:1 /NFL /NDL /NP /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "AI pack kopyalama hatasi (robocopy code=$LASTEXITCODE)"
    }
} else {
    Write-Host "[3/6] Offline AI pack atlandi." -ForegroundColor Yellow
}

Write-Host "[4/6] Setup baslatma dosyalari yaziliyor..." -ForegroundColor Cyan
$launcher = @"
@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title YazKlinik D700 Windows Setup

set "TARGET=D:\YazKlinik_Final_D700"
echo.
echo ============================================================
echo  YazKlinik D700 kurulum basliyor
echo  Kaynak: %~dp0APP_SOURCE
echo  Hedef : %TARGET%
echo ============================================================
echo.
pause

if not exist "%~dp0APP_SOURCE\D700_ILK_KURULUM.bat" (
  echo [HATA] APP_SOURCE eksik veya bozuk.
  pause
  exit /b 1
)

robocopy "%~dp0APP_SOURCE" "%TARGET%" /E /R:1 /W:1 /NFL /NDL /NP /NJH /NJS
if errorlevel 8 (
  echo [HATA] Dosya kopyalama basarisiz.
  pause
  exit /b 1
)

echo.
echo MedGemma kurulumu secin:
echo   1^) Online (internetten ollama/model indir)
if exist "%~dp0MEDGEMMA_OLLAMA_PACK\PACK_REPORT.json" (
  echo   2^) Offline (paketten kur)
) else (
  echo   2^) Offline yok (AI pack bulunamadi)
)
echo   3^) Simdilik gec
set /p _mgs=Secim [1/2/3]:

if "%_mgs%"=="1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%TARGET%\MEDGEMMA_KURULUM_ONLINE.ps1" -DownloadHfModels
) else if "%_mgs%"=="2" (
  if exist "%~dp0MEDGEMMA_OLLAMA_PACK\PACK_REPORT.json" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%TARGET%\MEDGEMMA_KURULUM_OFFLINE.ps1" -PackRoot "%~dp0MEDGEMMA_OLLAMA_PACK"
  ) else (
    echo [UYARI] Offline AI pack bulunamadi, atlandi.
  )
)

echo.
echo Ilk kurulum baslatiliyor...
call "%TARGET%\D700_ILK_KURULUM.bat"
endlocal
"@
Set-Content -LiteralPath (Join-Path $OutputRoot "KURULUM_BASLAT.bat") -Value $launcher -Encoding ASCII

$quickReadme = @"
YAZKLINIK D700 WINDOWS SETUP

1) Yeni PC'de USB/diski takin.
2) Bu klasorden KURULUM_BASLAT.bat calistirin.
3) Kurulum tamamlaninca D:\YazKlinik_Final_D700\D700_BASLAT.bat ile acilis yapin.

Not:
- Offline AI pack varsa secim ekraninda 2 secilebilir.
- Ilk kurulumda internet yoksa offline ai pack secin.
"@
Set-Content -LiteralPath (Join-Path $OutputRoot "KURULUM_OKU_BENI.txt") -Value $quickReadme -Encoding ASCII

Write-Host "[5/6] Boyut raporu olusturuluyor..." -ForegroundColor Cyan
$appGb = Get-DirSizeGb -Path $appOut
$packGb = if ($IncludeOfflineAiPack) { Get-DirSizeGb -Path (Join-Path $OutputRoot "MEDGEMMA_OLLAMA_PACK") } else { 0.0 }
$totalGb = Get-DirSizeGb -Path $OutputRoot
$report = [pscustomobject]@{
    output_root = $OutputRoot
    created_at = (Get-Date).ToString("s")
    include_offline_ai_pack = [bool]$IncludeOfflineAiPack
    app_source_gb = $appGb
    offline_ai_pack_gb = $packGb
    total_gb = $totalGb
}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $OutputRoot "SETUP_REPORT.json") -Encoding UTF8

Write-Host "[6/6] Tamamlandi." -ForegroundColor Green
Write-Host ("[OK] Kurulum klasoru: {0}" -f $OutputRoot) -ForegroundColor Green
Write-Host ("[OK] Toplam boyut: {0} GB" -f $totalGb) -ForegroundColor Green
