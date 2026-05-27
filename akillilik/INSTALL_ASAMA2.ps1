# YazKlinik D700 - AKILLILIK PAKETI ASAMA 2
# Tarih: 2026-05-17
#
# Bu script AÅAMA 0+1 tamamlandiktan sonra calistirilir:
#   - Tesseract OCR binary (e-Nabiz taranmis PDF metnini cikar)
#   - Poppler binary (pdf2image gercek calismasi icin)
#   - Restic + ilk yedek hatti
#   - 3D Slicer (tibbi goruntu analizi)
#   - Obsidian (kisisel not + wiki)
#   - Zotero (makale yonetimi)
#   - OHIF Viewer + Stirling-PDF Docker ekleri (compose up)
#
# Kullanim:
#   .\INSTALL_ASAMA2.ps1              # default DryRun
#   .\INSTALL_ASAMA2.ps1 -Run         # gercekten kur
#   .\INSTALL_ASAMA2.ps1 -Run -SkipPoppler -SkipRestic   # parca atla

[CmdletBinding()]
param(
    [switch]$Run = $false,
    [switch]$SkipWinget = $false,
    [switch]$SkipPoppler = $false,
    [switch]$SkipRestic = $false,
    [switch]$SkipDocker = $false,
    [string]$ProjectRoot = "D:\YazKlinik_Final_D500"
)

$ErrorActionPreference = "Continue"
$start = Get-Date

function Step($m,$c="Cyan") { Write-Host ""; Write-Host "===> $m" -ForegroundColor $c }
function OK($m)   { Write-Host "  OK  $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  !!  $m" -ForegroundColor Yellow }
function Err($m)  { Write-Host "  XX  $m" -ForegroundColor Red }

if (-not $Run) {
    Warn "DRY-RUN. Gercek kurulum icin: .\INSTALL_ASAMA2.ps1 -Run"
}
Step "ASAMA 2 baslangic: $($start.ToString('HH:mm:ss'))"

# === 1) Winget (Tesseract + 3D Slicer + Obsidian + Zotero + Restic) =========
if (-not $SkipWinget) {
    Step "Windows uygulamalari (winget)"
    $apps = @(
        @{id="UB-Mannheim.TesseractOCR"; name="Tesseract OCR (Turkce + Ingilizce)"}
        @{id="Slicer.Slicer";            name="3D Slicer (tibbi goruntu)"}
        @{id="Obsidian.Obsidian";        name="Obsidian (notlar + wiki)"}
        @{id="Zotero.Zotero";            name="Zotero (makale yonetimi)"}
        @{id="restic.restic";            name="Restic (sifreli yedek)"}
    )
    foreach ($a in $apps) {
        if (-not $Run) {
            Write-Host "  [DRY] winget install $($a.id)  # $($a.name)"
            continue
        }
        Write-Host -NoNewline "  -> $($a.name)..."
        $r = winget install --id $a.id -e --silent --accept-source-agreements --accept-package-agreements --disable-interactivity 2>&1
        if ($LASTEXITCODE -eq 0) { Write-Host " OK" -ForegroundColor Green }
        elseif ($r -match "already installed|exists already") { Write-Host " ZATEN VAR" -ForegroundColor Yellow }
        else { Write-Host " ATLA (cikis $LASTEXITCODE)" -ForegroundColor Yellow }
    }
}

# === 2) Poppler (PDF rasterize, manuel zip) ================================
if (-not $SkipPoppler) {
    Step "Poppler Windows binary (manuel zip)"
    $popDir = "$ProjectRoot\tools\poppler"
    if (Test-Path "$popDir\Library\bin\pdftoppm.exe") {
        OK "Poppler zaten kurulu: $popDir"
    } elseif (-not $Run) {
        Write-Host "  [DRY] poppler-windows latest zip indir + $popDir altina ac"
    } else {
        try {
            $url = "https://github.com/oschwartz10612/poppler-windows/releases/download/v24.08.0-0/Release-24.08.0-0.zip"
            $zip = "$env:TEMP\poppler-yk.zip"
            Write-Host -NoNewline "  -> indiriliyor (~30 MB)..."
            Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing -TimeoutSec 60
            Write-Host " OK" -ForegroundColor Green

            Write-Host -NoNewline "  -> aciliyor..."
            New-Item -ItemType Directory -Path $popDir -Force -EA SilentlyContinue | Out-Null
            Expand-Archive -Path $zip -DestinationPath $popDir -Force
            Remove-Item $zip -EA SilentlyContinue
            # Tek alt klasor olabilir, dogru bin'i bul
            $binDir = Get-ChildItem -Path $popDir -Recurse -Filter "pdftoppm.exe" -EA SilentlyContinue |
                      Select-Object -First 1 -ExpandProperty DirectoryName
            if ($binDir) {
                Write-Host " OK -> $binDir" -ForegroundColor Green
                # PATH'e ekle (kullanici scope)
                $existing = [Environment]::GetEnvironmentVariable("Path","User")
                if ($existing -notlike "*$binDir*") {
                    [Environment]::SetEnvironmentVariable("Path", "$existing;$binDir", "User")
                    OK "PATH'e eklendi (yeni terminal'de aktif)"
                }
            } else {
                Err "pdftoppm.exe bulunamadi - $popDir kontrol et"
            }
        } catch {
            Err "Poppler kurulum hatasi: $_"
        }
    }
}

# === 3) Restic yedek hatti =================================================
if (-not $SkipRestic) {
    Step "Restic ilk yedek deposu"
    $resticRepo = "$ProjectRoot\backup\restic-repo"
    $resticPass = "$ProjectRoot\backup\.restic-pass"

    if (-not $Run) {
        Write-Host "  [DRY] Repo init: $resticRepo"
        Write-Host "  [DRY] Ilk yedek: yazklinik_v68.sqlite3 + rag_data + akillilik/data"
    } else {
        $restic = Get-Command restic -EA SilentlyContinue
        if (-not $restic) {
            Warn "restic CLI henuz PATH'de degil (winget yeni kurmussa terminal'i kapat-ac)"
        } else {
            if (-not (Test-Path $resticRepo)) {
                New-Item -ItemType Directory -Path "$ProjectRoot\backup" -Force | Out-Null
                # Random repo parolasi
                $pass = -join ((1..32) | ForEach-Object { '{0:X}' -f (Get-Random -Max 16) })
                $pass | Out-File -FilePath $resticPass -Encoding ascii -NoNewline
                $env:RESTIC_PASSWORD = $pass
                $env:RESTIC_REPOSITORY = $resticRepo
                Write-Host -NoNewline "  -> repo init..."
                restic init 2>&1 | Out-Null
                if ($LASTEXITCODE -eq 0) { Write-Host " OK" -ForegroundColor Green; Write-Host "  PAROLA: $resticPass" }
                else { Err "init basarisiz"; return }
            } else {
                OK "Repo zaten var: $resticRepo"
                $env:RESTIC_PASSWORD_FILE = $resticPass
                $env:RESTIC_REPOSITORY = $resticRepo
            }
            Write-Host -NoNewline "  -> ilk yedek aliniyor..."
            $env:RESTIC_PASSWORD_FILE = $resticPass
            restic backup `
                "$ProjectRoot\local_db" `
                "$ProjectRoot\rag_data" `
                "$ProjectRoot\akillilik\data" `
                "$ProjectRoot\static" `
                "$ProjectRoot\config.env" `
                --tag d700-akillilik `
                --tag (Get-Date -Format yyyy-MM-dd) `
                2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) { Write-Host " OK" -ForegroundColor Green }
            else { Err "Backup hata $LASTEXITCODE" }
        }
    }
}

# === 4) Docker yeni servisler (OHIF + Stirling-PDF) =========================
if (-not $SkipDocker) {
    Step "Docker stack: OHIF + Stirling-PDF ekle"
    $stackDir = "$ProjectRoot\akillilik"
    Set-Location $stackDir

    # STIRLING_ADMIN_PASSWORD .env'e ekle (yoksa)
    $envFile = "$stackDir\.env"
    $envText = if (Test-Path $envFile) { Get-Content $envFile -Raw } else { "" }
    if ($envText -notmatch "STIRLING_ADMIN_PASSWORD") {
        $sp = -join ((1..16) | ForEach-Object { '{0:X}' -f (Get-Random -Max 16) })
        if (-not $Run) {
            Write-Host "  [DRY] .env'e STIRLING_ADMIN_PASSWORD ekle"
        } else {
            Add-Content -Path $envFile -Value "`nSTIRLING_ADMIN_PASSWORD=$sp" -Encoding utf8
            OK "Stirling-PDF admin parolasi: admin / $sp  (.env'de)"
        }
    }

    if (-not $Run) {
        Write-Host "  [DRY] docker compose pull ohif-viewer stirling-pdf"
        Write-Host "  [DRY] docker compose up -d ohif-viewer stirling-pdf"
    } else {
        Write-Host "  -> image pull..."
        docker compose pull ohif-viewer stirling-pdf 2>&1 | Select-Object -Last 4
        Write-Host "  -> compose up..."
        docker compose up -d ohif-viewer stirling-pdf 2>&1 | Select-Object -Last 6
        Start-Sleep 5
        $ohif = curl.exe -s -o NUL -w "%{http_code}" http://localhost:13003/ --max-time 5 2>$null
        $stir = curl.exe -s -o NUL -w "%{http_code}" http://localhost:13004/ --max-time 5 2>$null
        Write-Host "  OHIF http://localhost:13003 -> $ohif"
        Write-Host "  Stirling http://localhost:13004 -> $stir"
    }
    Set-Location $ProjectRoot
}

# === 5) JITSI MEET (manuel, ayri yonergeyle) ===============================
Step "Jitsi Meet (manuel)"
Write-Host "  Jitsi Meet yapilandirma istegen icin (.env + docker-jitsi-meet repo + LE cert)"
Write-Host "  ayri olarak akillilik/jitsi/ klasorunde hazirlandi:"
Write-Host "    cd D:\YazKlinik_Final_D500\akillilik\jitsi"
Write-Host "    cp env.example .env"
Write-Host "    (.env icindeki PUBLIC_URL'i Tailscale Funnel adresinle degistir)"
Write-Host "    docker compose up -d"

# === OZET ===
Step "OZET" "Green"
$dur = ((Get-Date) - $start).TotalMinutes
Write-Host "  Toplam sure: $([math]::Round($dur, 1)) dk"
if (-not $Run) {
    Warn "DRY-RUN'di. -Run ile gercek calistir"
} else {
    OK "ASAMA 2 bitti!"
    Write-Host "  Yeni URL'ler:"
    Write-Host "    OHIF Viewer  : http://localhost:13003"
    Write-Host "    Stirling PDF : http://localhost:13004  (admin / .env'deki parola)"
    Write-Host "  Yeni Windows app'ler (Start menu):"
    Write-Host "    Tesseract OCR, 3D Slicer, Obsidian, Zotero, Restic"
    Write-Host "  Yedek deposu: $ProjectRoot\backup\restic-repo"
    Write-Host ""
    Write-Host "  Yeni terminalde tesseract --version  / pdftoppm --version  ile dogrula"
    Write-Host "  Verify: .\VERIFY_AKILLILIK.ps1"
}


