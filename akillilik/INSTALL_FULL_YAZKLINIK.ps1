# YazKlinik FULL Master Installer - Tek Tik Kurulum
# Tarih: 2026-05-17 (Session 7)
# Kullanim: PowerShell admin olarak:
#   Set-ExecutionPolicy -Scope Process Bypass -Force
#   .\INSTALL_FULL_YAZKLINIK.ps1 [-SkipDocker] [-SkipPython] [-Run]
#
# Bu script Asama 1 + 2 + 3 (akillilik paketi) + Session 6 (PostgreSQL+Redis+Meilisearch)
# + Session 7 (29 yeni ajan + PWA + uyumluluk) icin gerekli her seyi yapar.

param(
    [switch]$SkipDocker,
    [switch]$SkipPython,
    [switch]$SkipDB,
    [switch]$Run = $false
)

$ErrorActionPreference = "Continue"
$projectRoot = "D:\YazKlinik_Final_D500"
$venv = "$projectRoot\.venv\Scripts\python.exe"

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " YazKlinik D700 FULL Installer (Session 7)   " -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

if (-not $Run) {
    Write-Host "Bu script soyle kurar:" -ForegroundColor Yellow
    Write-Host "  - Asama 1: BGE-M3 RAG + meditron + Ollama paketleri"
    Write-Host "  - Asama 2: OHIF + Stirling-PDF + Tesseract + Poppler + Restic + Obsidian + Zotero + 3D Slicer"
    Write-Host "  - Asama 3: PostgreSQL + Redis + MeiliSearch (Docker)"
    Write-Host "  - Session 7: 29 yeni ajan + 38 endpoint + PWA + DB tablo migration"
    Write-Host "  - Final: Server restart + smoke test"
    Write-Host ""
    Write-Host "Calistirmak icin -Run ekle:" -ForegroundColor Green
    Write-Host "  .\INSTALL_FULL_YAZKLINIK.ps1 -Run"
    Write-Host ""
    Write-Host "Atlamak istediklerinizi ekle:" -ForegroundColor Gray
    Write-Host "  -SkipDocker     Asama 3'u atla (Docker zaten varsa)"
    Write-Host "  -SkipPython     Asama 1 python paketleri atla"
    Write-Host "  -SkipDB         DB migration atla"
    exit 0
}

Write-Host "[1/6] Asama 1 - Python AI paketleri" -ForegroundColor Yellow
if (-not $SkipPython) {
    $req1 = @"
FlagEmbedding>=1.2.10
rerankers>=0.5.0
sentence_transformers>=2.7.0
faster_whisper>=1.0.0
requests>=2.31
pillow>=10.0
"@
    $tmpReq = New-TemporaryFile
    Set-Content -Path $tmpReq.FullName -Value $req1 -Encoding ascii
    & $venv -m pip install -q -r $tmpReq.FullName
    Remove-Item $tmpReq.FullName -ErrorAction SilentlyContinue
    Write-Host "  [OK] Python AI paketleri kuruldu" -ForegroundColor Green
} else {
    Write-Host "  [--] Atlandi" -ForegroundColor Gray
}

Write-Host ""
Write-Host "[2/6] Asama 1b - Ollama modelleri" -ForegroundColor Yellow
$models = @("bge-m3:latest", "qwen2.5:32b", "meditron:70b", "yaz:latest", "llama3.2-vision:11b")
foreach ($m in $models) {
    Write-Host -NoNewline "  Pulling $m ... "
    $out = ollama pull $m 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK]" -ForegroundColor Green
    } else {
        Write-Host "[!!] Skip (Ollama yok veya model mevcut)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "[3/6] Asama 2 - Yardimci kurulumlar (winget)" -ForegroundColor Yellow
$tools = @(
    @{Id="UB-Mannheim.TesseractOCR"; Name="Tesseract OCR"},
    @{Id="oschwartz10612.Poppler"; Name="Poppler PDF"},
    @{Id="restic.restic"; Name="Restic Backup"},
    @{Id="Obsidian.Obsidian"; Name="Obsidian"},
    @{Id="DigitalScholar.Zotero"; Name="Zotero"},
    @{Id="Slicer.Slicer"; Name="3D Slicer"}
)
foreach ($t in $tools) {
    Write-Host -NoNewline "  Installing $($t.Name) ... "
    $r = winget install --id $t.Id --silent --accept-source-agreements --accept-package-agreements 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0 -or $r -match "already installed") {
        Write-Host "[OK]" -ForegroundColor Green
    } else {
        Write-Host "[!!] Manual gerek" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "[4/6] Asama 3 - Docker Compose (PostgreSQL + Redis + MeiliSearch + n8n + ...)" -ForegroundColor Yellow
if (-not $SkipDocker) {
    $dockerRunning = (docker ps 2>&1 | Out-String) -notmatch "error"
    if (-not $dockerRunning) {
        Write-Host "  Docker Desktop baslatiliyor..." -ForegroundColor Yellow
        Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe" -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 30
    }
    Set-Location "$projectRoot\akillilik"
    docker compose up -d 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Docker compose 9 servis baslatildi" -ForegroundColor Green
    } else {
        Write-Host "  [!!] Docker compose hatasi - manuel kontrol" -ForegroundColor Yellow
    }
    Set-Location $projectRoot
} else {
    Write-Host "  [--] Atlandi (-SkipDocker)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "[5/6] Session 7 - DB Migration (audit_log + consent + 2fa + ...)" -ForegroundColor Yellow
if (-not $SkipDB) {
    & $venv -c "import sys; sys.path.insert(0, r'$projectRoot'); import yazklinik_db_migrate_agent as m; r = m.migrate_all(); print(f'applied={r.applied} skipped={r.skipped} failed={r.failed}')"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] DB migration tamam" -ForegroundColor Green
    } else {
        Write-Host "  [XX] DB migration hata" -ForegroundColor Red
    }
} else {
    Write-Host "  [--] Atlandi (-SkipDB)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "[6/6] Server restart + smoke test" -ForegroundColor Yellow
# Mevcut server'i durdur
Get-NetTCPConnection -LocalPort 5443 -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

# Yeniden baslat (D500_BASLAT.bat var ise)
$startBat = "$projectRoot\D500_BASLAT.bat"
if (Test-Path $startBat) {
    Start-Process -FilePath $startBat -WindowStyle Hidden
    Write-Host "  Server baslatiliyor..."
    Start-Sleep -Seconds 8
}

# Smoke
$smokeOk = $false
try {
    $r = curl.exe -sk -o NUL -w "%{http_code}" https://127.0.0.1:5443/api/status --max-time 10 2>$null
    if ($r -eq "200") {
        $smokeOk = $true
        Write-Host "  [OK] /api/status calisiyor" -ForegroundColor Green
    }
} catch { }

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " KURULUM TAMAM " -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

if ($smokeOk) {
    Write-Host "  Adresler:" -ForegroundColor Green
    Write-Host "    https://127.0.0.1:5443           (ana)"
    Write-Host "    https://127.0.0.1:5443/ajanlar   (ajan dashboard)"
    Write-Host "    https://127.0.0.1:5443/status    (PUBLIC durum)"
    Write-Host "    https://127.0.0.1:5443/uyumluluk (ISO+KVKK)"
    Write-Host "    https://127.0.0.1:5443/dashboard"
    Write-Host ""
    Write-Host "  Sonraki adim:" -ForegroundColor Yellow
    Write-Host "    .\VERIFY_AKILLILIK.ps1   (tam smoke test)"
} else {
    Write-Host "  [!!] Server canli degil - manuel kontrol:" -ForegroundColor Yellow
    Write-Host "    D500_BASLAT.bat (cift tikla)"
    Write-Host "    veya powershell ile baslat"
}
Write-Host ""

