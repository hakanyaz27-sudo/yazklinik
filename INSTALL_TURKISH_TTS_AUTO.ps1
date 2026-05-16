# YazKlinik D300 - Windows TR TTS Auto-installer (no prompt)
# Caglrilabilirligi: Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File <bu_dosya>"
# Log: D:\YazKlinik_Final_D300\INSTALL_TURKISH_TTS_AUTO.log

$ErrorActionPreference = "Continue"
$logPath = "D:\YazKlinik_Final_D300\INSTALL_TURKISH_TTS_AUTO.log"
Start-Transcript -Path $logPath -Force | Out-Null

function Section($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function Ok($t) { Write-Host "[OK] $t" -ForegroundColor Green }
function Warn($t) { Write-Host "[!] $t" -ForegroundColor Yellow }
function Fail($t) { Write-Host "[HATA] $t" -ForegroundColor Red }

Section "Admin kontrolu"
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Fail "Yonetici degil. UAC kabul edilmemis."
    "INSTALL_FAIL_NOT_ADMIN" | Out-File "D:\YazKlinik_Final_D300\INSTALL_TURKISH_TTS_AUTO.status" -Encoding ASCII -Force
    Stop-Transcript | Out-Null
    exit 1
}
Ok "Yonetici yetkisi var"

Section "Mevcut TR sesler"
try {
    $voice = New-Object -ComObject SAPI.SpVoice
    foreach ($v in $voice.GetVoices()) { Write-Host ("  - " + $v.GetDescription()) }
} catch { Warn "SAPI hata: $_" }

Section "TR capabilities yukleniyor"
$targets = @(
    "Language.Speech~~~tr-TR~0.0.1.0",
    "Language.TextToSpeech~~~tr-TR~0.0.1.0",
    "Language.Basic~~~tr-TR~0.0.1.0",
    "Language.OCR~~~tr-TR~0.0.1.0",
    "Language.Handwriting~~~tr-TR~0.0.1.0"
)
foreach ($t in $targets) {
    try {
        $cap = Get-WindowsCapability -Online -Name $t -ErrorAction Stop
        if ($cap.State -eq "Installed") {
            Ok "Zaten yuklu: $t"
        } else {
            Write-Host "[+] Yukleniyor: $t" -ForegroundColor Cyan
            Add-WindowsCapability -Online -Name $t -ErrorAction Stop | Out-Null
            Ok "Yuklendi: $t"
        }
    } catch {
        Fail "HATA $t : $_"
    }
}

Section "Registry OneCore -> SAPI mirror (Win11 Tolga/Sedef)"
$regBase = "HKLM:\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens"
$onecoreTokens = Get-ChildItem $regBase -ErrorAction SilentlyContinue | Where-Object {
    $_.PSChildName -like "*TR-TR*" -or $_.PSChildName -like "*Tolga*" -or $_.PSChildName -like "*Sedef*"
}
if ($onecoreTokens) {
    $sapiBase = "HKLM:\SOFTWARE\Microsoft\Speech\Voices\Tokens"
    foreach ($t in $onecoreTokens) {
        $dst = Join-Path $sapiBase $t.PSChildName
        if (-not (Test-Path $dst)) {
            try {
                Copy-Item -Path $t.PSPath -Destination $sapiBase -Recurse -Force -ErrorAction Stop
                Ok "SAPI mirror: $($t.PSChildName)"
            } catch { Warn "Mirror hata: $($t.PSChildName) : $_" }
        } else {
            Ok "Zaten SAPI'de: $($t.PSChildName)"
        }
    }
} else {
    Warn "OneCore'da TR voice token yok - Windows Update veya dil paketi gerekebilir."
}

Section "Yukleme sonrasi TR sesler"
try {
    $voice2 = New-Object -ComObject SAPI.SpVoice
    $trVoices = @()
    foreach ($v in $voice2.GetVoices()) {
        $desc = $v.GetDescription()
        Write-Host ("  - " + $desc)
        if ($desc -match "Turkish|Turkce|Tolga|Sedef|TR-TR") { $trVoices += $desc }
    }
    Section "Sonuc"
    if ($trVoices.Count -gt 0) {
        Ok ("TR ses bulundu: " + ($trVoices -join ", "))
        "INSTALL_OK_TR_VOICES=$($trVoices.Count)" | Out-File "D:\YazKlinik_Final_D300\INSTALL_TURKISH_TTS_AUTO.status" -Encoding ASCII -Force
    } else {
        Warn "Capabilities yuklendi ama SAPI'de TR ses gorunmedi. Yeniden baslatma gerekebilir."
        "INSTALL_PARTIAL_REBOOT_NEEDED" | Out-File "D:\YazKlinik_Final_D300\INSTALL_TURKISH_TTS_AUTO.status" -Encoding ASCII -Force
    }
} catch {
    Fail "SAPI son kontrol hata: $_"
    "INSTALL_FAIL_SAPI" | Out-File "D:\YazKlinik_Final_D300\INSTALL_TURKISH_TTS_AUTO.status" -Encoding ASCII -Force
}

Stop-Transcript | Out-Null
