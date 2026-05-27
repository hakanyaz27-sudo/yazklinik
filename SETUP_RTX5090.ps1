# YazKlinik D700 - RTX 5090 PC sifirdan kurulum scripti
# YONETICI olarak calistirilmali (SETUP_RTX5090.bat tetikler)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Section($t) {
    Write-Host ""
    Write-Host ("============================================================") -ForegroundColor Cyan
    Write-Host (" " + $t) -ForegroundColor Cyan
    Write-Host ("============================================================") -ForegroundColor Cyan
}
function Ok($t) { Write-Host ("  [OK] " + $t) -ForegroundColor Green }
function Warn($t) { Write-Host ("  [!] " + $t) -ForegroundColor Yellow }
function Fail($t) { Write-Host ("  [HATA] " + $t) -ForegroundColor Red }
function Info($t) { Write-Host ("  [i] " + $t) -ForegroundColor White }

Section "YazKlinik D700 - RTX 5090 Sifirdan Kurulum"

# === 0) Admin check ===
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Fail "Yonetici yetkisi gerekli. SETUP_RTX5090.bat ile calistir."
    Read-Host "Enter ile cik"
    exit 1
}
Ok "Yonetici yetkisi OK"

# === 1) Klasor + hedef yol ===
$installRoot = "D:\YazKlinik_Final_D500"
if (-not (Test-Path $installRoot)) {
    Info "Hedef klasor olusturulacak: $installRoot"
    New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
}
Set-Location $installRoot

# === 2) Python 3.11/3.12 kontrolu ===
Section "1. Python kontrolu"
$pyVersions = @()
$pyExe = $null
try {
    $pyOut = & py -0 2>&1 | Out-String
    foreach ($l in ($pyOut -split "`n")) {
        if ($l -match "(3\.(11|12))") { $pyVersions += $matches[0] }
    }
} catch {}

if ($pyVersions.Count -eq 0) {
    Warn "Python 3.11/3.12 bulunamadi"
    Info "Yukleniyor: Python 3.12 (winget ile)..."
    try {
        winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
        Ok "Python 3.12 yuklendi"
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","User")
    } catch {
        Fail "winget Python yukleyemedi. https://www.python.org/downloads/ den el ile yukle, sonra bu scripti tekrar calistir."
        Read-Host "Enter ile cik"
        exit 1
    }
} else {
    Ok ("Python bulundu: " + ($pyVersions -join ", "))
}

# Python yolu (sirayla 3.12, 3.11)
$pyExe = $null
foreach ($v in @("3.12","3.11")) {
    try {
        $candidate = (& py -$v -c "import sys; print(sys.executable)" 2>$null).Trim()
        if ($candidate -and (Test-Path $candidate)) { $pyExe = $candidate; break }
    } catch {}
}
if (-not $pyExe) { Fail "Python yolu bulunamadi"; exit 1 }
Ok "Python: $pyExe"

# === 3) Sanal ortam (.venv) ===
Section "2. Sanal ortam (.venv) hazirla"
$venvPath = Join-Path $installRoot ".venv"
if (Test-Path $venvPath) {
    Warn "Eski .venv var, korunuyor (yenilemek icin manuel sil)"
} else {
    & $pyExe -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { Fail "venv olusturulamadi"; exit 1 }
    Ok ".venv olusturuldu"
}
$venvPy = Join-Path $venvPath "Scripts\python.exe"
$venvPip = Join-Path $venvPath "Scripts\pip.exe"

# === 4) pip upgrade + requirements ===
Section "3. Python paketleri (pip install -r requirements.txt)"
& $venvPy -m pip install --upgrade pip setuptools wheel 2>&1 | Out-Null
Ok "pip upgrade OK"

if (-not (Test-Path "requirements.txt")) {
    Fail "requirements.txt yok. Tasinan dosyalar arasinda olmali."
    exit 1
}

Info "Paketler yukleniyor (5-15 dakika)..."
& $venvPy -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Warn "Bazi paketler basarisiz - log'a bak"
} else {
    Ok "Tum paketler yuklendi"
}

# === 5) CUDA destegi (RTX 5090 icin) ===
Section "4. CUDA destegi (RTX 5090)"
Info "NVIDIA driver kontrolu..."
$nvidia = $false
try {
    $smi = & nvidia-smi 2>&1 | Out-String
    if ($smi -match "RTX|NVIDIA") {
        $nvidia = $true
        Ok "NVIDIA GPU algilandi"
    }
} catch {}

if (-not $nvidia) {
    Warn "nvidia-smi calismadi. NVIDIA driver yuklu mu?"
    Info "GeForce driver: https://www.nvidia.com/Download/index.aspx"
}

# faster-whisper CUDA destegi icin cuBLAS + cuDNN gerek
Info "cuBLAS + cuDNN pip ile yukleniyor (faster-whisper CUDA backend)..."
& $venvPy -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Ok "cuBLAS + cuDNN yuklendi"
} else {
    Warn "cuBLAS yukleme basarisiz - sistem CUDA Toolkit varsa yine calisir"
}

# === 6) Whisper modelleri ===
Section "5. Whisper modeller (small + large-v3)"
$hfCachePath = Join-Path $env:USERPROFILE ".cache\huggingface\hub"
Info "Model cache: $hfCachePath"

Info "Small model indiriliyor (hizli yedek)..."
& $venvPy -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')" 2>&1 | Out-Null
Ok "small model OK"

Info "Large-v3 model indiriliyor (1.5 GB - dakikalar surebilir)..."
& $venvPy -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cpu', compute_type='int8')" 2>&1 | Out-Null
Ok "large-v3 model OK (CUDA'da fp16 ile calisacak)"

# === 7) Klasor + DB hazirligi ===
Section "6. Klasor yapilandirma"
@("local_db", "auto_backups", "data", "exports", "voice_records", "dicom_cache",
  "local_multimedia", "temp", "runtime_state", "certs") | ForEach-Object {
    $d = Join-Path $installRoot $_
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null; Info "Olusturuldu: $_" }
}
Ok "Klasor yapisi hazir"

# === 8) HTTPS sertifika ===
Section "7. HTTPS sertifikasi"
$certCrt = Join-Path $installRoot "certs\yazklinik_https.crt"
$certKey = Join-Path $installRoot "certs\yazklinik_https.key"
if ((Test-Path $certCrt) -and (Test-Path $certKey)) {
    Ok "Sertifika mevcut, korunuyor"
} else {
    Info "Self-signed sertifika olusturuluyor..."
    & $venvPy -c "from cryptography import x509; from cryptography.x509.oid import NameOID; from cryptography.hazmat.primitives import hashes, serialization; from cryptography.hazmat.primitives.asymmetric import rsa; from datetime import datetime, timedelta; import ipaddress; key = rsa.generate_private_key(public_exponent=65537, key_size=2048); subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'YazKlinik')]); cert = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(datetime.utcnow()).not_valid_after(datetime.utcnow() + timedelta(days=3650)).add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'), x509.IPAddress(ipaddress.IPv4Address('127.0.0.1'))]), critical=False).sign(key, hashes.SHA256()); open(r'$certCrt','wb').write(cert.public_bytes(serialization.Encoding.PEM)); open(r'$certKey','wb').write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))"
    if ((Test-Path $certCrt) -and (Test-Path $certKey)) {
        Ok "Sertifika olusturuldu (10 yil gecerli)"
    } else {
        Warn "Sertifika olusturulamadi - HTTPS calismayabilir"
    }
}

# === 9) Ollama (opsiyonel - LLM icin) ===
Section "8. Ollama (LLM icin - opsiyonel)"
$ollamaInstalled = $null
try {
    $ollamaInstalled = (Get-Command ollama -ErrorAction SilentlyContinue)
} catch {}

if ($ollamaInstalled) {
    Ok "Ollama yuklu"
} else {
    Warn "Ollama yok"
    Info "Yuklemek istersen: https://ollama.com/download/windows"
    Info "Yukledikten sonra: ollama pull llama3.1:8b veya qwen2.5:14b"
}

# === 10) Windows Turkce TTS (Tolga/Sedef) ===
Section "9. Windows Turkce TTS"
Info "Turkce konusma yetenekleri yukleniyor..."
$ttsCaps = @(
    "Language.Speech~~~tr-TR~0.0.1.0",
    "Language.TextToSpeech~~~tr-TR~0.0.1.0",
    "Language.Basic~~~tr-TR~0.0.1.0"
)
foreach ($t in $ttsCaps) {
    try {
        $cap = Get-WindowsCapability -Online -Name $t -ErrorAction Stop
        if ($cap.State -ne "Installed") {
            Add-WindowsCapability -Online -Name $t -ErrorAction Stop | Out-Null
            Info "Yuklendi: $t"
        }
    } catch {
        Warn ("Atlandi: " + $t + " ($_)")
    }
}
Ok "TR TTS adimi tamamlandi"

# === 11) config.env RTX 5090 profili ===
Section "10. config.env (RTX 5090 profili)"
if (Test-Path "config.rtx5090.env") {
    if (Test-Path "config.env") {
        Warn "config.env mevcut - korunuyor. RTX ayarlari icin elle config.rtx5090.env'i kopyala."
    } else {
        Copy-Item "config.rtx5090.env" "config.env"
        Ok "config.env -> RTX 5090 profili"
    }
} else {
    Warn "config.rtx5090.env yok - varsayilan kullanilacak"
}

# === SON ===
Section "KURULUM TAMAM"
Write-Host ""
Write-Host "  Sirada:" -ForegroundColor Cyan
Write-Host "    1. Windows'u yeniden baslat (TR TTS sesleri aktif olsun)"
Write-Host "    2. NVIDIA Driver son surume guncellenmis mi kontrol et"
Write-Host "    3. D500_BASLAT.bat'i cift tikla"
Write-Host "    4. https://127.0.0.1:5443 (doktor / 1234)"
Write-Host ""
Write-Host "  Hata olursa:" -ForegroundColor Yellow
Write-Host "    D500_server.log + D500_whisper_service.log dosyalarini paylas"
Write-Host ""
Read-Host "Enter ile cik"

