[CmdletBinding()]
param(
    [string]$ProjectRoot = "D:\YazKlinik_Final_D700",
    [string]$PackRoot = "D:\YazKlinik_Final_D700\MEDGEMMA_OLLAMA_PACK",
    [switch]$EnableMedgemma = $true
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Step($msg) { Write-Host ""; Write-Host ("===> " + $msg) -ForegroundColor Cyan }
function Ok($msg) { Write-Host ("  [OK] " + $msg) -ForegroundColor Green }
function Warn($msg) { Write-Host ("  [!] " + $msg) -ForegroundColor Yellow }
function Fail($msg) { Write-Host ("  [HATA] " + $msg) -ForegroundColor Red }

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Test-OllamaApi {
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300)
    } catch {
        return $false
    }
}

function Get-OllamaExePath {
    $cmd = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }
    $fallback = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path -LiteralPath $fallback) { return $fallback }
    return ""
}

function Ensure-OllamaOnline {
    param([string]$OllamaExe)
    if (Test-OllamaApi) { return }
    if (-not $OllamaExe) { throw "ollama.exe bulunamadi." }
    Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden
    for ($i = 0; $i -lt 40; $i++) {
        if (Test-OllamaApi) { return }
        Start-Sleep -Seconds 1
    }
    throw "Ollama API acilamadi (11434)."
}

function Parse-OllamaListNames {
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

function Set-ConfigValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $lines = Get-Content -LiteralPath $Path -Encoding UTF8
    $updated = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        if ($line -match ("^\s*" + [regex]::Escape($Key) + "=")) {
            $lines[$i] = "$Key=$Value"
            $updated = $true
            break
        }
    }
    if (-not $updated) {
        $lines += "$Key=$Value"
    }
    Set-Content -LiteralPath $Path -Value $lines -Encoding UTF8
}

Step "Offline MedGemma + Ollama kurulum"
Ensure-Directory -Path $ProjectRoot
Set-Location $ProjectRoot

$packRuntime = Join-Path $PackRoot "ollama-runtime"
$packHf = Join-Path $PackRoot "models"
$packOllama = Join-Path $PackRoot "ollama-user-models-medgemma"

if (-not (Test-Path -LiteralPath $packRuntime)) { throw "Pack runtime yok: $packRuntime" }
if (-not (Test-Path -LiteralPath $packHf)) { throw "Pack models yok: $packHf" }
if (-not (Test-Path -LiteralPath $packOllama)) { Warn ("Pack ollama modeli yok: " + $packOllama) }

Step "Ollama runtime kopyalama"
$runtimeTarget = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
Ensure-Directory -Path $runtimeTarget
robocopy $packRuntime $runtimeTarget /E /R:1 /W:1 /NFL /NDL /NP /NJH /NJS | Out-Null
Ok ("Runtime hedef: " + $runtimeTarget)

Step "PATH kontrolu"
$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ";") -notcontains $runtimeTarget) {
    if ($userPath) {
        [System.Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $runtimeTarget), "User")
    } else {
        [System.Environment]::SetEnvironmentVariable("Path", $runtimeTarget, "User")
    }
    Ok "User PATH guncellendi."
} else {
    Ok "User PATH zaten uygun."
}
$env:Path = $runtimeTarget + ";" + $env:Path

Step "HF MedGemma dosyalari kopyalama"
$hfTarget = Join-Path $ProjectRoot "models"
Ensure-Directory -Path $hfTarget
robocopy $packHf $hfTarget /E /R:1 /W:1 /NFL /NDL /NP /NJH /NJS | Out-Null
Ok ("HF hedef: " + $hfTarget)

Step "Ollama manifests+blobs kopyalama"
$ollamaModelsTarget = Join-Path $env:USERPROFILE ".ollama\models"
Ensure-Directory -Path $ollamaModelsTarget
if (Test-Path -LiteralPath $packOllama) {
    robocopy $packOllama $ollamaModelsTarget /E /R:1 /W:1 /NFL /NDL /NP /NJH /NJS | Out-Null
    Ok ("Ollama model hedefi: " + $ollamaModelsTarget)
} else {
    Warn "Pack icinde ollama model artefakti yok; sadece runtime + HF kopyalandi."
}

Step "Ollama servis dogrulama"
$ollamaExe = Get-OllamaExePath
if (-not $ollamaExe) {
    throw "ollama.exe bulunamadi (runtime kopyasi kontrol edilmeli)."
}
Ensure-OllamaOnline -OllamaExe $ollamaExe
Ok "Ollama API aktif (11434)."

if ($EnableMedgemma) {
    Step "config.env guncelleme"
    $configPath = Join-Path $ProjectRoot "config.env"
    Set-ConfigValue -Path $configPath -Key "YAZKLINIK_MEDGEMMA_ENABLED" -Value "1"
    Set-ConfigValue -Path $configPath -Key "YAZKLINIK_MEDGEMMA_BACKEND" -Value "auto"
    Set-ConfigValue -Path $configPath -Key "YAZKLINIK_HF_HOME" -Value ($hfTarget.Replace("\", "\\") + "\\huggingface")
    Ok "config.env medgemma ayarlari guncellendi."
}

Step "Dogrulama"
$names = Parse-OllamaListNames
$mg = @($names | Where-Object { $_.ToLower().Contains("medgemma") })
if ($mg.Count -gt 0) {
    Ok ("Ollama MedGemma modeller: " + ($mg -join ", "))
} else {
    Warn "Ollama icinde medgemma gorunmuyor. Pack manifets/blobs eksik olabilir."
}

$reportDir = Join-Path $ProjectRoot "runtime_state"
Ensure-Directory -Path $reportDir
$reportPath = Join-Path $reportDir ("MEDGEMMA_OFFLINE_INSTALL_REPORT_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".json")
$report = [pscustomobject]@{
    mode = "offline"
    project_root = $ProjectRoot
    pack_root = $PackRoot
    ollama_models_detected = @($mg)
    medgemma_enabled = [bool]$EnableMedgemma
    finished_at = (Get-Date).ToString("s")
}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8
Ok ("Rapor: " + $reportPath)
