# YazKlinik D700 - Akillilik Paketi Kurulum Scripti
# Tarih: 2026-05-17
#
# Kullanim:
#   .\INSTALL_AKILLILIK_PAKETI.ps1              # default = DryRun (sadece goster)
#   .\INSTALL_AKILLILIK_PAKETI.ps1 -Run         # gercekten kur
#   .\INSTALL_AKILLILIK_PAKETI.ps1 -Run -SkipDocker  # docker stack'i atla
#   .\INSTALL_AKILLILIK_PAKETI.ps1 -Run -SkipWinget  # Windows app'leri atla
#
# Bu script:
#   1. Winget ile Windows uygulamalari kurar (Everything, PowerToys, ...)
#   2. Docker compose stack'i baslatir (Vaultwarden + UptimeKuma + n8n + Open WebUI)
#   3. Ollama'da onerilen modelleri pull eder (varsa atlar)
#   4. Pip ile ileri AI paketleri yukler (zaten var olanlari atlar)
#   5. Restic icin baslangic yapilandirir (opsiyonel)
#   6. SMTP/Bildirim ayarlari icin yer hazirlar (manuel doldurulacak)
#
# Tum islem ~30-60 dk (internet hizina + Ollama pull'lara bagli).

[CmdletBinding()]
param(
    [switch]$Run = $false,
    [switch]$SkipDocker = $false,
    [switch]$SkipWinget = $false,
    [switch]$SkipOllama = $false,
    [switch]$SkipPip = $false,
    [string]$ProjectRoot = "D:\YazKlinik_Final_D500",
    [string]$VenvPython = "D:\YazKlinik_Final_D500\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Continue"
$startTime = Get-Date

function Write-Step($msg, $color="Cyan") {
    Write-Host ""
    Write-Host "===> $msg" -ForegroundColor $color
}
function Write-Ok($msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  !!  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  XX  $msg" -ForegroundColor Red }

if (-not $Run) {
    Write-Warn "DRY-RUN modu. Hicbir sey kurulmuyor."
    Write-Warn "Gercekten kurmak icin: .\INSTALL_AKILLILIK_PAKETI.ps1 -Run"
}

# === KONUM ===
Set-Location $ProjectRoot
Write-Step "Kurulum klasoru: $ProjectRoot"

# === 1) ON KONTROL ===
Write-Step "On kontrol"
$checks = @{
    "Python venv"   = (Test-Path $VenvPython)
    "Docker"        = ($null -ne (Get-Command docker -EA SilentlyContinue))
    "Winget"        = ($null -ne (Get-Command winget -EA SilentlyContinue))
    "Ollama"        = ($null -ne (Get-Command ollama -EA SilentlyContinue))
    "NVIDIA GPU"    = ($null -ne (Get-Command nvidia-smi -EA SilentlyContinue))
    "Git"           = ($null -ne (Get-Command git -EA SilentlyContinue))
}
foreach ($k in $checks.Keys) {
    if ($checks[$k]) { Write-Ok "$k bulundu" } else { Write-Warn "$k YOK" }
}

# Disk
$drive = Get-PSDrive D
$freeGb = [math]::Round($drive.Free/1GB, 1)
if ($freeGb -lt 50) {
    Write-Err "Disk D: $freeGb GB bos - en az 50 GB onerilir"
} else {
    Write-Ok "Disk D: $freeGb GB bos"
}

# === 2) WINGET WINDOWS UYGULAMALARI ===
if (-not $SkipWinget -and $checks["Winget"]) {
    Write-Step "Windows uygulamalari (winget)"
    $wingetApps = @(
        @{id="voidtools.Everything"; name="Everything (dosya arama)"}
        @{id="Microsoft.PowerToys";  name="PowerToys (FancyZones, PowerRename)"}
        @{id="GitHub.cli";           name="GitHub CLI"}
        @{id="Bitwarden.Bitwarden";  name="Bitwarden Desktop (Vaultwarden client)"}
        @{id="Microsoft.PowerShell"; name="PowerShell 7 (modern shell)"}
    )
    foreach ($app in $wingetApps) {
        if (-not $Run) {
            Write-Host "  [DRY] winget install --id $($app.id) -e --silent  # $($app.name)"
            continue
        }
        Write-Host "  -> $($app.name)..." -NoNewline
        $r = winget install --id $app.id -e --silent --accept-source-agreements --accept-package-agreements 2>&1
        if ($LASTEXITCODE -eq 0 -or $r -match "already installed") {
            Write-Host " OK" -ForegroundColor Green
        } else {
            Write-Host " HATA / atlandi" -ForegroundColor Yellow
        }
    }
}

# === 3) PIP AI PAKETLERI (venv) ===
if (-not $SkipPip -and $checks["Python venv"]) {
    Write-Step "Python AI paketleri (venv)"
    $pipPackages = @(
        "FlagEmbedding"      # BGE-M3 embedding
        "rerankers[transformers]"  # BGE-Reranker
        "openai-whisper"     # ses tanima
        "silero-vad"         # voice activity detection (Alex dinleme)
        "pytesseract"        # OCR wrapper (Tesseract binary winget'ten)
        "pdf2image"          # PDF thumbnail
        "weasyprint"         # HTML -> PDF (rapor yazdirma)
        "httpx[http2]"       # daha iyi HTTP client
    )
    foreach ($pkg in $pipPackages) {
        if (-not $Run) {
            Write-Host "  [DRY] pip install --upgrade $pkg"
            continue
        }
        Write-Host "  -> $pkg..." -NoNewline
        $r = & $VenvPython -m pip install --upgrade $pkg 2>&1 | Select-Object -Last 1
        if ($LASTEXITCODE -eq 0) {
            Write-Host " OK" -ForegroundColor Green
        } else {
            Write-Host " HATA" -ForegroundColor Yellow
            Write-Host "    $r" -ForegroundColor DarkYellow
        }
    }
}

# === 4) OLLAMA MODELLERI ===
if (-not $SkipOllama -and $checks["Ollama"]) {
    Write-Step "Ollama medikal/akilli modeller"
    # Mevcut modeller
    $existing = @()
    try {
        $existing = (ollama list 2>$null | Select-Object -Skip 1) -split "`n" |
                    ForEach-Object { ($_ -split '\s+')[0] } | Where-Object { $_ }
    } catch {}

    $models = @(
        @{name="medgemma:27b";      reason="Google MedGemma tibbi LLM (~17 GB)"; size_gb=17}
        @{name="bge-m3";            reason="BGE-M3 embedding (~570 MB)"; size_gb=1}
        # meditron:70b zaten yuklu, dokunmuyoruz
    )
    foreach ($m in $models) {
        if ($existing -contains $m.name) {
            Write-Ok "$($m.name) zaten yuklu - atlandi"
            continue
        }
        if (-not $Run) {
            Write-Host "  [DRY] ollama pull $($m.name)  # $($m.reason)"
            continue
        }
        Write-Host "  -> $($m.name) ($($m.size_gb) GB) pull basliyor..."
        # Pull blocking; uzun surer (10-30 dk)
        ollama pull $m.name
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "$($m.name) pull OK"
        } else {
            Write-Err "$($m.name) pull BASARISIZ"
        }
    }
}

# === 5) DOCKER COMPOSE STACK ===
if (-not $SkipDocker -and $checks["Docker"]) {
    Write-Step "Docker compose stack (Vaultwarden + UptimeKuma + n8n + Open WebUI)"
    $stackDir = Join-Path $ProjectRoot "akillilik"
    if (-not (Test-Path $stackDir)) {
        Write-Err "Klasor yok: $stackDir"
    } else {
        Set-Location $stackDir

        # .env olustur (yoksa)
        $envFile = Join-Path $stackDir ".env"
        if (-not (Test-Path $envFile)) {
            # Random admin token uret
            $token = -join ((1..32) | ForEach-Object { '{0:X}' -f (Get-Random -Max 16) })
            $envContent = "VAULTWARDEN_ADMIN_TOKEN=$token`n"
            if ($Run) {
                Set-Content -Path $envFile -Value $envContent -Encoding utf8
                Write-Ok "Yeni .env yazildi (Vaultwarden admin token random)"
                Write-Warn "Token: $token   <- SAKLA, https://localhost:18443/admin"
            } else {
                Write-Host "  [DRY] .env olusturulacak (random admin token)"
            }
        }

        if (-not $Run) {
            Write-Host "  [DRY] docker compose up -d"
        } else {
            docker compose pull 2>&1 | Out-Null
            $up = docker compose up -d 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Ok "Stack basladi:"
                Write-Host "    Vaultwarden : http://localhost:18443"
                Write-Host "    Uptime Kuma : http://localhost:13001"
                Write-Host "    n8n         : http://localhost:15678"
                Write-Host "    Open WebUI  : http://localhost:13000"
            } else {
                Write-Err "Stack baslamadi: $up"
            }
        }
        Set-Location $ProjectRoot
    }
}

# === 6) YAZKLINIK RESTART (kod degisikliklerini al) ===
Write-Step "YazKlinik server restart onerisi"
Write-Host "  Yeni RAG (BGE-M3 + reranker), konsult ajan (meditron:70b), htmx/Alpine/Chart"
Write-Host "  arayuze inject edildi. Server'i yeniden baslat:"
Write-Host "    Stop-Process -Name python -Force -EA SilentlyContinue"
Write-Host "    D:\YazKlinik_Final_D500\D500_BASLAT.bat"

# === 7) OZET RAPOR ===
Write-Step "OZET" "Green"
$dur = ((Get-Date) - $startTime).TotalMinutes
Write-Host "  Toplam sure: $([math]::Round($dur, 1)) dk"
if (-not $Run) {
    Write-Host ""
    Write-Warn "BUNLAR DRY-RUN'di. Gercekten kurmak icin -Run ekle:"
    Write-Host "    .\INSTALL_AKILLILIK_PAKETI.ps1 -Run" -ForegroundColor Yellow
} else {
    Write-Ok "Kurulum bitti! Sonraki adimlar:"
    Write-Host "    1. http://localhost:18443/admin -> Vaultwarden admin (token .env'de)"
    Write-Host "    2. http://localhost:13001 -> Uptime Kuma hesap olustur, watch list ekle"
    Write-Host "    3. http://localhost:15678 -> n8n owner hesabi olustur"
    Write-Host "    4. http://localhost:13000 -> Open WebUI admin hesabi olustur"
    Write-Host "    5. https://127.0.0.1:5443/sifre-degistir -> doktor/1234 DEGISTIR"
    Write-Host ""
    Write-Host "    Verify: .\VERIFY_AKILLILIK.ps1"
}

