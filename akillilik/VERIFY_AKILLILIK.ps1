# YazKlinik D300 - Akillilik Dogrulama Scripti
# Tarih: 2026-05-17
# Kullanim: .\VERIFY_AKILLILIK.ps1

$ErrorActionPreference = "Continue"
$venv = "D:\YazKlinik_Final_D300\.venv\Scripts\python.exe"
$projectRoot = "D:\YazKlinik_Final_D300"
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
    try {
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}
        $r = Invoke-WebRequest -Uri "https://127.0.0.1:5443/giris" -UseBasicParsing -TimeoutSec 5
        $r.Headers["X-YK-Server"] -eq "D300"
    } catch { $false }
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
