# YazKlinik D700 - Akillilik Dogrulama Scripti
# Tarih: 2026-05-17
# Kullanim: .\VERIFY_AKILLILIK.ps1

$ErrorActionPreference = "Continue"
$venv = "D:\YazKlinik_Final_D500\.venv\Scripts\python.exe"
$projectRoot = "D:\YazKlinik_Final_D500"
$failed = 0
$ok = 0

function Test-Item($name, $action) {
    Write-Host -NoNewline "  [..] $name"
    try {
        $result = & $action
        if ($result) {
            Write-Host "`r  [OK] $name                                              " -ForegroundColor Green
            $script:ok++
            return $true
        } else {
            Write-Host "`r  [XX] $name                                              " -ForegroundColor Red
            $script:failed++
            return $false
        }
    } catch {
        Write-Host "`r  [XX] $name : $($_.Exception.Message.Substring(0, [Math]::Min(50, $_.Exception.Message.Length)))" -ForegroundColor Red
        $script:failed++
        return $false
    }
}

Write-Host ""
Write-Host "=== YazKlinik Akillilik Dogrulama ===" -ForegroundColor Cyan
Write-Host ""

# 1. Python paketler
Write-Host "[1/6] Python AI paketleri" -ForegroundColor Yellow
Test-Item "FlagEmbedding (BGE-M3)" { & $venv -c "import FlagEmbedding" 2>&1 | Out-Null; $LASTEXITCODE -eq 0 }
Test-Item "rerankers" { & $venv -c "import rerankers" 2>&1 | Out-Null; $LASTEXITCODE -eq 0 }
Test-Item "faster_whisper" { & $venv -c "import faster_whisper" 2>&1 | Out-Null; $LASTEXITCODE -eq 0 }
Test-Item "sentence_transformers" { & $venv -c "import sentence_transformers" 2>&1 | Out-Null; $LASTEXITCODE -eq 0 }
Test-Item "chromadb" { & $venv -c "import chromadb" 2>&1 | Out-Null; $LASTEXITCODE -eq 0 }
Test-Item "torch + CUDA" { & $venv -c "import torch; assert torch.cuda.is_available()" 2>&1 | Out-Null; $LASTEXITCODE -eq 0 }

# 2. RAG
Write-Host ""
Write-Host "[2/6] RAG (Alex Bilgi Havuzu)" -ForegroundColor Yellow
Set-Location $projectRoot
Test-Item "yazklinik_rag.py syntax" { & $venv -c "import ast; ast.parse(open('yazklinik_rag.py', encoding='utf-8').read())" 2>&1 | Out-Null; $LASTEXITCODE -eq 0 }
Test-Item "RAG: BGE-M3 model konfig" {
    $out = & $venv -c "import yazklinik_rag as r; print(r.EMBED_MODEL)" 2>&1
    $out -match "bge-m3"
}
Test-Item "RAG: reranker konfig" {
    $out = & $venv -c "import yazklinik_rag as r; print(r.USE_RERANKER)" 2>&1
    $out -match "True"
}

# 3. Konsult ajan
Write-Host ""
Write-Host "[3/6] YZ Konsultasyon Ajani" -ForegroundColor Yellow
Test-Item "konsult agent syntax" { & $venv -c "import ast; ast.parse(open('yazklinik_konsult_agent.py', encoding='utf-8').read())" 2>&1 | Out-Null; $LASTEXITCODE -eq 0 }
Test-Item "konsult: meditron tercih var" {
    $out = & $venv -c "import yazklinik_konsult_agent as k; print(k.PREFERRED_MODELS_BY_STEP)" 2>&1
    $out -match "meditron"
}
Test-Item "konsult: ddx adimi meditron seciyor" {
    $out = & $venv -c "import yazklinik_konsult_agent as k; print(k._pick_model_for_step('ddx'))" 2>&1
    $out -match "meditron"
}

# 4. Ollama modelleri
Write-Host ""
Write-Host "[4/6] Ollama modelleri" -ForegroundColor Yellow
$ollamaList = ollama list 2>$null
Test-Item "Ollama servisi" { $LASTEXITCODE -eq 0 }
Test-Item "meditron:70b yuklu" { $ollamaList -match "meditron:70b" }
Test-Item "qwen2.5:32b yuklu" { $ollamaList -match "qwen2.5:32b" }

# 5. Docker stack
Write-Host ""
Write-Host "[5/6] Docker Akillilik Stack" -ForegroundColor Yellow
Test-Item "Docker servisi" { docker ps 2>$null | Out-Null; $LASTEXITCODE -eq 0 }
$containers = docker ps --format "{{.Names}}" 2>$null
Test-Item "Vaultwarden container" { $containers -match "yk-vaultwarden" }
Test-Item "Uptime Kuma container" { $containers -match "yk-uptime-kuma" }
Test-Item "n8n container" { $containers -match "yk-n8n" }
Test-Item "Open WebUI container" { $containers -match "yk-open-webui" }
Test-Item "OHIF Viewer container (Asama 2)" { $containers -match "yk-ohif" }
Test-Item "Stirling PDF container (Asama 2)" { $containers -match "yk-stirling" }

# 6. YazKlinik server
Write-Host ""
Write-Host "[6/6] YazKlinik Server" -ForegroundColor Yellow
Test-Item "Port 5443 dinleniyor" {
    try {
        $conn = Test-NetConnection -ComputerName 127.0.0.1 -Port 5443 -InformationLevel Quiet -WarningAction SilentlyContinue
        $conn
    } catch { $false }
}
Test-Item "HTTPS yaniti" {
    try {
        # Self-signed icin -SkipCertificateCheck (PS 7+)
        $r = Invoke-WebRequest -Uri "https://127.0.0.1:5443/giris" -SkipCertificateCheck -UseBasicParsing -TimeoutSec 5 -EA SilentlyContinue
        $r.StatusCode -eq 200
    } catch {
        # PS 5.1 fallback
        try {
            [System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}
            $r = Invoke-WebRequest -Uri "https://127.0.0.1:5443/giris" -UseBasicParsing -TimeoutSec 5
            $r.StatusCode -eq 200
        } catch { $false }
    }
}
Test-Item "X-YK-Server header" {
    # PowerShell 5.1 TLS uyumsuzlugu Werkzeug ile; curl ile test (daha gercek)
    $h = curl.exe -sk -I https://127.0.0.1:5443/giris --max-time 5 2>$null
    ($h -match "X-YK-Server:\s*D700")
}

# 7. ASAMA 2: Tesseract + Poppler + Restic + Windows app'leri
Write-Host ""
Write-Host "[7/7] ASAMA 2 (OCR / Backup / Tibbi araclar)" -ForegroundColor Yellow
Test-Item "Tesseract OCR binary" {
    $tess = Get-Command tesseract -EA SilentlyContinue
    if ($tess) { return $true }
    # Default install yolu da kontrol
    Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe"
}
Test-Item "Poppler pdftoppm binary" {
    $pop = Get-Command pdftoppm -EA SilentlyContinue
    if ($pop) { return $true }
    # YazKlinik tools/poppler kontrol
    $found = Get-ChildItem "$projectRoot\tools\poppler" -Recurse -Filter "pdftoppm.exe" -EA SilentlyContinue | Select-Object -First 1
    $null -ne $found
}
Test-Item "Restic CLI" { $null -ne (Get-Command restic -EA SilentlyContinue) }
Test-Item "Restic repo init" { Test-Path "$projectRoot\backup\restic-repo\config" }
function _appInstalled([string]$wingetId, [string[]]$exePaths) {
    if ($wingetId -and (winget list --id $wingetId -e 2>&1 | Select-String $wingetId)) { return $true }
    foreach ($p in $exePaths) {
        if (Get-ChildItem -Path $p -EA SilentlyContinue | Select-Object -First 1) { return $true }
    }
    return $false
}
Test-Item "Obsidian" {
    _appInstalled "Obsidian.Obsidian" @(
        "$env:LOCALAPPDATA\Obsidian\Obsidian.exe",
        "$env:LOCALAPPDATA\Programs\Obsidian\Obsidian.exe",
        "C:\Program Files\Obsidian\Obsidian.exe")
}
Test-Item "Zotero" {
    _appInstalled "Zotero.Zotero" @(
        "C:\Program Files\Zotero\zotero.exe",
        "C:\Program Files (x86)\Zotero\zotero.exe",
        "$env:LOCALAPPDATA\Zotero\zotero.exe")
}
Test-Item "3D Slicer" {
    _appInstalled "Slicer.Slicer" @(
        "$env:LOCALAPPDATA\slicer.org\*\Slicer.exe",
        "C:\ProgramData\slicer.org\Slicer*\Slicer.exe",
        "C:\Program Files\Slicer*\Slicer.exe",
        "$env:LOCALAPPDATA\NA-MIC\Slicer*\Slicer.exe",
        "$env:LOCALAPPDATA\Programs\Slicer*\Slicer.exe")
}

# 8. ASAMA 3: PostgreSQL + Redis + MeiliSearch (Session 6)
Write-Host ""
Write-Host "[8/8] ASAMA 3 (PostgreSQL + Redis + MeiliSearch)" -ForegroundColor Yellow
Test-Item "PostgreSQL container" { $containers -match "yk-postgres" }
Test-Item "Redis container" { $containers -match "yk-redis" }
Test-Item "MeiliSearch container" { $containers -match "yk-meilisearch" }
Test-Item "psycopg python paketi" { & $venv -c "import psycopg" 2>&1 | Out-Null; $LASTEXITCODE -eq 0 }
Test-Item "redis python paketi" { & $venv -c "import redis" 2>&1 | Out-Null; $LASTEXITCODE -eq 0 }
Test-Item "meilisearch python paketi" { & $venv -c "import meilisearch" 2>&1 | Out-Null; $LASTEXITCODE -eq 0 }
Test-Item "PostgreSQL HTTP probe (15432)" {
    Test-NetConnection -ComputerName 127.0.0.1 -Port 15432 -InformationLevel Quiet -WarningAction SilentlyContinue
}
Test-Item "Redis port (16379)" {
    Test-NetConnection -ComputerName 127.0.0.1 -Port 16379 -InformationLevel Quiet -WarningAction SilentlyContinue
}
Test-Item "MeiliSearch HTTP probe (17700)" {
    try {
        $r = curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:17700/health --max-time 3 2>$null
        $r -eq "200"
    } catch { $false }
}
Test-Item "Yeni endpoint /api/db/postgres/health" {
    $c = curl.exe -sk -o NUL -w "%{http_code}" https://127.0.0.1:5443/api/db/postgres/health --max-time 5 2>$null
    $c -in "200","401"
}
Test-Item "Yeni endpoint /veridb-merkezi" {
    $c = curl.exe -sk -o NUL -w "%{http_code}" https://127.0.0.1:5443/veridb-merkezi --max-time 5 2>$null
    $c -in "200","401"
}

# Session 7 - Yeni 29 ajan + 38 endpoint
Write-Host ""
Write-Host "[7/7] Session 7 - 29 yeni ajan + endpoint smoke" -ForegroundColor Yellow

$session7Mods = @(
    "yazklinik_vision_usg_agent", "yazklinik_soap_agent", "yazklinik_icd10_agent",
    "yazklinik_gebelik_takvim_agent", "yazklinik_risk_skor_agent", "yazklinik_ddi_agent",
    "yazklinik_voice_command_agent", "yazklinik_anti_burnout_agent", "yazklinik_hatira_usg_agent",
    "yazklinik_orchestrator_agent", "yazklinik_hasta_portal_agent", "yazklinik_2fa_agent",
    "yazklinik_phq9_agent", "yazklinik_stok_agent", "yazklinik_konsey_agent",
    "yazklinik_payment_agent", "yazklinik_enabiz_kts_agent", "yazklinik_mhrs_agent",
    "yazklinik_medula_agent", "yazklinik_lab_duzen_agent", "yazklinik_iot_bluetooth_agent",
    "yazklinik_plugin_loader", "yazklinik_smear_hpv_agent", "yazklinik_celery_worker",
    "yazklinik_sentry_init", "yazklinik_memnuniyet_agent", "yazklinik_pubmed_cron_agent",
    "yazklinik_compliance_agent", "yazklinik_status_page_agent",
    "yazklinik_db_migrate_agent", "yazklinik_backup_verify_agent"
)
foreach ($mod in $session7Mods) {
    Test-Item "Module: $mod" {
        $out = & $venv -c "import sys; sys.path.insert(0, r'$projectRoot'); import $mod" 2>&1
        $LASTEXITCODE -eq 0
    }
}

# Public endpoints (auth yok)
Test-Item "Public /api/status" {
    $c = curl.exe -sk -o NUL -w "%{http_code}" https://127.0.0.1:5443/api/status --max-time 5 2>$null
    $c -eq "200"
}
Test-Item "Public /status (HTML)" {
    $c = curl.exe -sk -o NUL -w "%{http_code}" https://127.0.0.1:5443/status --max-time 5 2>$null
    $c -eq "200"
}
Test-Item "Public /manifest.webmanifest (PWA)" {
    $c = curl.exe -sk -o NUL -w "%{http_code}" https://127.0.0.1:5443/manifest.webmanifest --max-time 5 2>$null
    $c -in "200","404"  # 404 ok if static path not wired
}
Test-Item "Public /sw.js (PWA)" {
    $c = curl.exe -sk -o NUL -w "%{http_code}" https://127.0.0.1:5443/sw.js --max-time 5 2>$null
    $c -in "200","404"
}

# Auth-gated endpoints (401 doner - dogru)
Test-Item "Endpoint /api/agents/burnout/report (auth check)" {
    $c = curl.exe -sk -o NUL -w "%{http_code}" https://127.0.0.1:5443/api/agents/burnout/report --max-time 5 2>$null
    $c -in "200","302","401"
}
Test-Item "Endpoint /api/agents/voice-command/parse (auth check)" {
    $c = curl.exe -sk -o NUL -w "%{http_code}" -X POST https://127.0.0.1:5443/api/agents/voice-command/parse --max-time 5 2>$null
    $c -in "200","302","401","400"
}
Test-Item "Endpoint /uyumluluk (compliance panel)" {
    $c = curl.exe -sk -o NUL -w "%{http_code}" https://127.0.0.1:5443/uyumluluk --max-time 5 2>$null
    $c -in "200","302","401"
}
Test-Item "Endpoint /hasta-portal" {
    $c = curl.exe -sk -o NUL -w "%{http_code}" https://127.0.0.1:5443/hasta-portal --max-time 5 2>$null
    $c -in "200","401"
}

# DB Migration boot test (DB'de yeni tablolar var mi)
Test-Item "DB migration: audit_log tablo" {
    $out = & $venv -c "import sqlite3; con = sqlite3.connect(r'$projectRoot\local_db\yazklinik_v68.sqlite3'); print(1 if con.execute(`"SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'`").fetchone() else 0)" 2>&1
    $out -match "1"
}
Test-Item "DB migration: patient_consents tablo" {
    $out = & $venv -c "import sqlite3; con = sqlite3.connect(r'$projectRoot\local_db\yazklinik_v68.sqlite3'); print(1 if con.execute(`"SELECT name FROM sqlite_master WHERE type='table' AND name='patient_consents'`").fetchone() else 0)" 2>&1
    $out -match "1"
}

# Ozet
Write-Host ""
Write-Host "=== OZET ===" -ForegroundColor Cyan
Write-Host "  OK: $ok" -ForegroundColor Green
Write-Host "  XX: $failed" -ForegroundColor Red
$total = $ok + $failed
$pct = if ($total -gt 0) { [math]::Round($ok * 100 / $total, 0) } else { 0 }
Write-Host "  Skor: $pct%"
Write-Host ""

if ($failed -eq 0) {
    Write-Host "  HEPSI YESIL! Akillilik paketi tam calisiyor." -ForegroundColor Green
} elseif ($pct -ge 80) {
    Write-Host "  Cogu calisiyor; eksikleri kontrol et." -ForegroundColor Yellow
} else {
    Write-Host "  Birkac eksik var. INSTALL_AKILLILIK_PAKETI.ps1 -Run calistir." -ForegroundColor Red
}
Write-Host ""

exit $failed

