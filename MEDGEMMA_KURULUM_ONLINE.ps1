[CmdletBinding()]
param(
    [string]$ProjectRoot = "D:\YazKlinik_Final_D700",
    [string[]]$OllamaModels = @("medgemma:27b"),
    [string[]]$HfModels = @("google/medgemma-4b-it", "google/medgemma-1.5-4b-it"),
    [switch]$DownloadHfModels = $true,
    [switch]$EnableMedgemma = $true
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Step($msg) { Write-Host ""; Write-Host ("===> " + $msg) -ForegroundColor Cyan }
function Ok($msg) { Write-Host ("  [OK] " + $msg) -ForegroundColor Green }
function Warn($msg) { Write-Host ("  [!] " + $msg) -ForegroundColor Yellow }
function Fail($msg) { Write-Host ("  [HATA] " + $msg) -ForegroundColor Red }

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

function Ensure-OllamaInstalled {
    $exe = Get-OllamaExePath
    if ($exe) { return $exe }

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Ollama yok ve winget bulunamadi."
    }

    Warn "Ollama bulunamadi, winget ile kuruluyor..."
    $ids = @("Ollama.Ollama", "Ollama.Ollama.Portable")
    foreach ($id in $ids) {
        try {
            & winget install --id $id -e --silent --accept-package-agreements --accept-source-agreements | Out-Null
        } catch {}
        Start-Sleep -Seconds 2
        $exe = Get-OllamaExePath
        if ($exe) {
            Ok ("Ollama kuruldu: " + $id)
            return $exe
        }
    }
    throw "Ollama kurulamadi."
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

function Pull-OllamaModels {
    param([string[]]$Models)
    $existing = Parse-OllamaListNames
    foreach ($m in @($Models | Where-Object { $_ -and $_.Trim() })) {
        $tag = $m.Trim()
        if ($existing -contains $tag) {
            Ok ("Ollama modeli zaten var: " + $tag)
            continue
        }
        Write-Host ("  -> ollama pull " + $tag)
        & ollama pull $tag
        if ($LASTEXITCODE -eq 0) {
            Ok ("Pull OK: " + $tag)
        } else {
            Warn ("Pull basarisiz: " + $tag)
        }
    }
}

function Ensure-HfModels {
    param(
        [string]$VenvPy,
        [string]$HfHome,
        [string[]]$Models
    )
    if (-not (Test-Path -LiteralPath $VenvPy)) {
        Warn (".venv python yok, HF model indirme atlandi: " + $VenvPy)
        return
    }
    Ensure-Directory -Path $HfHome
    $tmpPy = Join-Path $env:TEMP "yk_medgemma_hf_download.py"
    $tmpJson = Join-Path $env:TEMP "yk_medgemma_models.json"
    $script = @"
import json
import os
import sys
from huggingface_hub import snapshot_download

hf_home = sys.argv[1]
models_file = sys.argv[2]
with open(models_file, "r", encoding="utf-8") as fh:
    models = json.load(fh)
os.environ["HF_HOME"] = hf_home
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

report = []
for model_id in models:
    model_id = str(model_id).strip()
    if not model_id:
        continue
    try:
        local_path = snapshot_download(repo_id=model_id, local_files_only=False)
        report.append({"model": model_id, "ok": True, "path": local_path})
    except Exception as exc:
        report.append({"model": model_id, "ok": False, "error": str(exc)})

print(json.dumps(report, ensure_ascii=True))
"@
    Set-Content -LiteralPath $tmpPy -Value $script -Encoding ASCII

    @($Models) | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $tmpJson -Encoding ASCII
    & $VenvPy -m pip install --upgrade 'huggingface_hub<1.0' | Out-Null
    $prevErr = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & $VenvPy $tmpPy $HfHome $tmpJson 2>&1
    $cmdExit = $LASTEXITCODE
    $ErrorActionPreference = $prevErr
    $lines = @($output | ForEach-Object { ("" + $_).Trim() } | Where-Object { $_ })
    $jsonLine = @($lines | Where-Object { $_.StartsWith("[") }) | Select-Object -Last 1
    $parsed = $null
    if ($jsonLine) {
        try { $parsed = $jsonLine | ConvertFrom-Json } catch {}
    }
    if ($parsed) {
        $failed = @($parsed | Where-Object { -not $_.ok })
        if ($failed.Count -eq 0) {
            Ok "HF MedGemma indirme adimi tamamlandi."
        } else {
            Warn ("HF MedGemma indirme kismi: {0}/{1} basarisiz." -f $failed.Count, @($parsed).Count)
            foreach ($row in $failed) {
                Warn ("  " + $row.model + " -> " + $row.error)
            }
        }
    } elseif ($cmdExit -eq 0) {
        Ok "HF MedGemma indirme adimi tamamlandi."
    } else {
        Warn "HF MedGemma indirme adiminda hata var."
        foreach ($line in $lines) { Write-Host ("  " + $line) }
    }
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
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

Step "Online MedGemma + Ollama kurulum"
Ensure-Directory -Path $ProjectRoot
Set-Location $ProjectRoot

$ollamaExe = Ensure-OllamaInstalled
Ok ("Ollama exe: " + $ollamaExe)

Step "Ollama servis dogrulama"
Ensure-OllamaOnline -OllamaExe $ollamaExe
Ok "Ollama API aktif (11434)."

Step "Ollama MedGemma pull"
Pull-OllamaModels -Models $OllamaModels

$hfHome = Join-Path $ProjectRoot "models\huggingface"
$venvPy = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if ($DownloadHfModels) {
    Step "Hugging Face MedGemma indirme"
    Ensure-HfModels -VenvPy $venvPy -HfHome $hfHome -Models $HfModels
}

if ($EnableMedgemma) {
    Step "config.env guncelleme"
    $configPath = Join-Path $ProjectRoot "config.env"
    Set-ConfigValue -Path $configPath -Key "YAZKLINIK_MEDGEMMA_ENABLED" -Value "1"
    Set-ConfigValue -Path $configPath -Key "YAZKLINIK_MEDGEMMA_BACKEND" -Value "auto"
    Set-ConfigValue -Path $configPath -Key "YAZKLINIK_HF_HOME" -Value ($hfHome.Replace("\", "\\"))
    Ok "config.env medgemma ayarlari guncellendi."
}

Step "Dogrulama"
$names = Parse-OllamaListNames
$mg = @($names | Where-Object { $_.ToLower().Contains("medgemma") })
if ($mg.Count -gt 0) {
    Ok ("Ollama MedGemma modeller: " + ($mg -join ", "))
} else {
    Warn "Ollama tarafinda medgemma modeli gorunmuyor."
}

$reportDir = Join-Path $ProjectRoot "runtime_state"
Ensure-Directory -Path $reportDir
$reportPath = Join-Path $reportDir ("MEDGEMMA_ONLINE_INSTALL_REPORT_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".json")
$report = [pscustomobject]@{
    mode = "online"
    project_root = $ProjectRoot
    ollama_models_requested = @($OllamaModels)
    ollama_models_detected = @($mg)
    hf_models_requested = @($HfModels)
    hf_download_enabled = [bool]$DownloadHfModels
    medgemma_enabled = [bool]$EnableMedgemma
    finished_at = (Get-Date).ToString("s")
}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8
Ok ("Rapor: " + $reportPath)
