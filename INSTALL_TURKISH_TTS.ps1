# YazKlinik D700 - Windows TÃ¼rkÃ§e TTS yÃ¼kleyici
# YONETICI olarak calistirin: sag tikla -> "PowerShell ile Yonetici olarak calistir"

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " YazKlinik - Windows Turkce Konusma Sesi (TTS) Yukleyici" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# 1) Admin kontrolu
$isAdmin = ([Security.Principal.WindowsPrincipal] `
            [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
              [Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Host "[HATA] Bu script YONETICI yetkisi ister." -ForegroundColor Red
    Write-Host "       Sag tikla > 'PowerShell ile Yonetici olarak calistir'" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Cikmak icin Enter"
    exit 1
}
Write-Host "[OK] Yonetici yetkisi var" -ForegroundColor Green

# 2) Mevcut durum
Write-Host ""
Write-Host "[i] Mevcut TTS sesleri:" -ForegroundColor Cyan
try {
    $voice = New-Object -ComObject SAPI.SpVoice
    foreach ($v in $voice.GetVoices()) {
        Write-Host ("    - " + $v.GetDescription())
    }
} catch {
    Write-Host "    SAPI hata: $_" -ForegroundColor Red
}

# 3) Yuklu Windows capabilities (Turkce)
Write-Host ""
Write-Host "[i] Turkce Konusma yetenekleri aranÄ±yor..." -ForegroundColor Cyan
$caps = Get-WindowsCapability -Online | Where-Object { $_.Name -like "*tr-TR*" }
foreach ($c in $caps) {
    $state = if ($c.State -eq "Installed") { "[YUKLU]" } else { "[YUKLU DEGIL]" }
    $color = if ($c.State -eq "Installed") { "Green" } else { "Yellow" }
    Write-Host ("    " + $state + " " + $c.Name) -ForegroundColor $color
}

# 4) Hedef paketler
$targets = @(
    "Language.Speech~~~tr-TR~0.0.1.0",
    "Language.TextToSpeech~~~tr-TR~0.0.1.0",
    "Language.OCR~~~tr-TR~0.0.1.0",
    "Language.Handwriting~~~tr-TR~0.0.1.0",
    "Language.Basic~~~tr-TR~0.0.1.0"
)

Write-Host ""
Write-Host "[i] Yuklenecek paketler:" -ForegroundColor Cyan
foreach ($t in $targets) {
    Write-Host ("    - " + $t)
}

Write-Host ""
Write-Host "[!] Yukleme baslar baslamaz BIRAZ ZAMAN ALABILIR (5-15 dakika)." -ForegroundColor Yellow
Write-Host "    Internet baglantisi GEREKLI." -ForegroundColor Yellow
Write-Host ""
$go = Read-Host "Devam etmek icin 'E' yaz, iptal icin baska bir tus"
if ($go -ne "E" -and $go -ne "e") {
    Write-Host "Iptal edildi." -ForegroundColor Yellow
    exit 0
}

# 5) Yukle
foreach ($t in $targets) {
    Write-Host ""
    Write-Host "[+] Yukleniyor: $t" -ForegroundColor Cyan
    try {
        $cap = Get-WindowsCapability -Online -Name $t -ErrorAction Stop
        if ($cap.State -eq "Installed") {
            Write-Host "    Zaten yuklu, atlandi." -ForegroundColor Green
        } else {
            Add-WindowsCapability -Online -Name $t -ErrorAction Stop | Out-Null
            Write-Host "    OK yuklendi" -ForegroundColor Green
        }
    } catch {
        Write-Host "    HATA: $_" -ForegroundColor Red
    }
}

# 6) Registry'den Tolga/Sedef speech voice tokenlarini etkinlestir (Windows 11 ek adim)
Write-Host ""
Write-Host "[i] Speech voice registry tokenleri kontrol ediliyor..." -ForegroundColor Cyan
$regBase = "HKLM:\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens"
$onecoreTokens = Get-ChildItem $regBase -ErrorAction SilentlyContinue |
    Where-Object { $_.PSChildName -like "*TR-TR*" -or $_.PSChildName -like "*Tolga*" -or $_.PSChildName -like "*Sedef*" }
if ($onecoreTokens) {
    Write-Host "    OneCore TR tokenler bulundu:" -ForegroundColor Green
    foreach ($t in $onecoreTokens) { Write-Host ("    - " + $t.PSChildName) }
    Write-Host ""
    Write-Host "    SAPI'ye kopyalaniyor (Win11'de Tolga/Sedef sadece OneCore'da, SAPI'ye manuel mirror gerek)..." -ForegroundColor Cyan
    $sapiBase = "HKLM:\SOFTWARE\Microsoft\Speech\Voices\Tokens"
    foreach ($t in $onecoreTokens) {
        $dst = Join-Path $sapiBase $t.PSChildName
        if (-not (Test-Path $dst)) {
            try {
                Copy-Item -Path $t.PSPath -Destination $sapiBase -Recurse -Force -ErrorAction Stop
                Write-Host ("    OK SAPI'ye kopyalandi: " + $t.PSChildName) -ForegroundColor Green
            } catch {
                Write-Host ("    HATA kopyalama: " + $_) -ForegroundColor Red
            }
        } else {
            Write-Host ("    Zaten SAPI'de: " + $t.PSChildName) -ForegroundColor Green
        }
    }
} else {
    Write-Host "    OneCore'da TR voice token bulunmadi - Windows guncelleme veya manuel dil paketi gerekebilir." -ForegroundColor Yellow
}

# 7) Sonuc
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Yukleme tamam. Yeniden baslatma SONRA TTS sesleri:" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
try {
    $voice2 = New-Object -ComObject SAPI.SpVoice
    foreach ($v in $voice2.GetVoices()) {
        Write-Host ("    - " + $v.GetDescription())
    }
} catch {
    Write-Host "    SAPI hata: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "[!] ONEMLI: TTS sesleri tam aktif olmasi icin Windows'u YENIDEN BASLATMANIZ gerekir." -ForegroundColor Yellow
Write-Host ""
Write-Host "    Test icin: Edge tarayicida F12 > Console:" -ForegroundColor Cyan
Write-Host "    > speechSynthesis.getVoices().filter(v=>v.lang.startsWith('tr'))" -ForegroundColor White
Write-Host ""
Read-Host "Cikmak icin Enter"

