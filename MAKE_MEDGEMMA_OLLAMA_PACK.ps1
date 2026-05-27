param(
    [string]$ProjectRoot = "D:\YazKlinik_Final_D700",
    [string]$PackRoot = "D:\YazKlinik_Final_D700\MEDGEMMA_OLLAMA_PACK",
    [string[]]$OllamaTags = @("medgemma:27b"),
    [switch]$EnsureOllamaModels = $false,
    [switch]$SkipHfCopy = $false
)

$ErrorActionPreference = "Stop"

function Get-DirSizeBytes {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    return (Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Parse-ModelTag {
    param([string]$ModelTag)
    $text = ("" + $ModelTag).Trim()
    if (-not $text) {
        return @{
            registry = "registry.ollama.ai"
            namespace = "library"
            model = "medgemma"
            tag = "27b"
        }
    }
    $namePart = $text
    $tagPart = "latest"
    if ($text.Contains(":")) {
        $parts = $text.Split(":", 2)
        $namePart = $parts[0].Trim()
        $tagPart = $parts[1].Trim()
        if (-not $tagPart) { $tagPart = "latest" }
    }
    $segments = $namePart.Split("/", [System.StringSplitOptions]::RemoveEmptyEntries)
    $namespace = "library"
    $model = $namePart
    if ($segments.Length -ge 2) {
        $namespace = ($segments[0..($segments.Length - 2)] -join "/")
        $model = $segments[-1]
    } elseif ($segments.Length -eq 1) {
        $model = $segments[0]
    }
    return @{
        registry = "registry.ollama.ai"
        namespace = $namespace
        model = $model
        tag = $tagPart
    }
}

function Copy-OllamaTagArtifacts {
    param(
        [string]$ModelTag,
        [string]$OllamaModelsRoot,
        [string]$DestRoot,
        [hashtable]$Stats
    )

    $parsed = Parse-ModelTag -ModelTag $ModelTag
    $manifestRel = Join-Path "manifests" (Join-Path $parsed.registry (Join-Path $parsed.namespace (Join-Path $parsed.model $parsed.tag)))
    $manifestSrc = Join-Path $OllamaModelsRoot $manifestRel
    if (-not (Test-Path -LiteralPath $manifestSrc)) {
        Write-Host ("  [!] Manifest yok: {0}" -f $ModelTag) -ForegroundColor Yellow
        return
    }

    $manifestDest = Join-Path $DestRoot $manifestRel
    Ensure-Directory -Path (Split-Path -Parent $manifestDest)
    Copy-Item -LiteralPath $manifestSrc -Destination $manifestDest -Force
    $Stats["manifest_count"] = [int]$Stats["manifest_count"] + 1

    $jsonText = Get-Content -LiteralPath $manifestSrc -Raw -Encoding UTF8
    $obj = $null
    try {
        $obj = $jsonText | ConvertFrom-Json
    } catch {
        Write-Host ("  [!] Manifest parse hatasi: {0}" -f $manifestSrc) -ForegroundColor Yellow
        return
    }

    $digests = New-Object System.Collections.Generic.HashSet[string]
    if ($obj.config -and $obj.config.digest) { [void]$digests.Add([string]$obj.config.digest) }
    if ($obj.layers) {
        foreach ($layer in $obj.layers) {
            if ($layer -and $layer.digest) { [void]$digests.Add([string]$layer.digest) }
        }
    }

    foreach ($d in $digests) {
        $clean = $d.Replace("sha256:", "").Trim()
        if (-not $clean) { continue }
        $blobRel = Join-Path "blobs" ("sha256-" + $clean)
        $blobSrc = Join-Path $OllamaModelsRoot $blobRel
        if (-not (Test-Path -LiteralPath $blobSrc)) { continue }
        $blobDest = Join-Path $DestRoot $blobRel
        Ensure-Directory -Path (Split-Path -Parent $blobDest)
        if (-not (Test-Path -LiteralPath $blobDest)) {
            Copy-Item -LiteralPath $blobSrc -Destination $blobDest -Force
            $Stats["blob_count"] = [int]$Stats["blob_count"] + 1
        }
    }
}

function Ensure-OllamaModel {
    param([string]$ModelTag)
    try {
        & ollama list | Out-Null
    } catch {
        Write-Host "  [!] ollama komutu calismiyor, pull atlandi." -ForegroundColor Yellow
        return
    }
    $existing = @()
    try {
        $existing = (& ollama list 2>$null | Select-Object -Skip 1) -split "`n" |
            ForEach-Object { ($_ -split '\s+')[0].Trim() } |
            Where-Object { $_ }
    } catch {}
    if ($existing -contains $ModelTag) {
        Write-Host ("  [OK] {0} zaten var." -f $ModelTag) -ForegroundColor Green
        return
    }
    Write-Host ("  [i] ollama pull {0}" -f $ModelTag)
    & ollama pull $ModelTag
}

Write-Host "[1/7] Hazirlik..."
Ensure-Directory -Path $PackRoot
$modelsOut = Join-Path $PackRoot "models"
$ollamaOut = Join-Path $PackRoot "ollama-runtime"
$ollamaModelOut = Join-Path $PackRoot "ollama-user-models-medgemma"
$scriptsOut = Join-Path $PackRoot "scripts"
Ensure-Directory -Path $modelsOut
Ensure-Directory -Path $ollamaOut
Ensure-Directory -Path $ollamaModelOut
Ensure-Directory -Path $scriptsOut

$projectModels = Join-Path $ProjectRoot "models"
$ollamaRuntime = "C:\Users\yazha\AppData\Local\Programs\Ollama"
$ollamaUserModels = "C:\Users\yazha\.ollama\models"

if ($EnsureOllamaModels) {
    Write-Host "[2/7] Ollama MedGemma modelleri dogrulaniyor/pull..."
    foreach ($t in ($OllamaTags | Where-Object { $_ -and $_.Trim() })) {
        Ensure-OllamaModel -ModelTag $t.Trim()
    }
}

Write-Host "[3/7] MedGemma HF dosyalari bulunuyor..."
$medgemmaFiles = @()
if ((-not $SkipHfCopy) -and (Test-Path -LiteralPath $projectModels)) {
    $medgemmaFiles = Get-ChildItem -LiteralPath $projectModels -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "medgemma" }
}
if ((-not $SkipHfCopy) -and ((-not $medgemmaFiles) -or $medgemmaFiles.Count -eq 0)) {
    throw "MedGemma dosyasi bulunamadi: $projectModels"
}

Write-Host "[4/7] MedGemma HF dosyalari kopyalaniyor..."
if ($SkipHfCopy) {
    Write-Host "  [i] HF kopya adimi atlandi (SkipHfCopy=1)."
} else {
    foreach ($f in $medgemmaFiles) {
        $relative = $f.FullName.Substring($projectModels.Length).TrimStart('\')
        $dest = Join-Path $modelsOut $relative
        Ensure-Directory -Path (Split-Path -Parent $dest)
        Copy-Item -LiteralPath $f.FullName -Destination $dest -Force
    }
}

Write-Host "[5/7] Ollama runtime kopyalaniyor..."
if (-not (Test-Path -LiteralPath $ollamaRuntime)) {
    throw "Ollama runtime bulunamadi: $ollamaRuntime"
}
robocopy $ollamaRuntime $ollamaOut /E /R:1 /W:1 /NFL /NDL /NP /NJH /NJS | Out-Null

Write-Host "[6/7] Ollama MedGemma manifests+blobs paketleniyor..."
$stats = @{
    manifest_count = 0
    blob_count = 0
}
if (Test-Path -LiteralPath $ollamaUserModels) {
    foreach ($t in ($OllamaTags | Where-Object { $_ -and $_.Trim() })) {
        Copy-OllamaTagArtifacts -ModelTag $t.Trim() -OllamaModelsRoot $ollamaUserModels -DestRoot $ollamaModelOut -Stats $stats
    }
} else {
    Write-Host "  [!] Ollama model klasoru yok, bu adim atlandi." -ForegroundColor Yellow
}

Write-Host "[7/7] Yardimci script + rapor..."
$installBat = @"
@echo off
setlocal
echo [INFO] Ollama runtime: %~dp0..\ollama-runtime
echo [INFO] MedGemma HF: %~dp0..\models
echo [INFO] Ollama MedGemma blobs/manifests: %~dp0..\ollama-user-models-medgemma
echo [INFO] Kurulum icin: MEDGEMMA_KURULUM_OFFLINE.ps1 kullan.
pause
"@
Set-Content -Path (Join-Path $scriptsOut "INSTALL_MEDGEMMA_OLLAMA_PACK.bat") -Value $installBat -Encoding ASCII

$packBytes = Get-DirSizeBytes -Path $PackRoot
$report = [pscustomobject]@{
    pack_root = $PackRoot
    pack_gb = [math]::Round($packBytes / 1GB, 3)
    medgemma_file_count = $medgemmaFiles.Count
    skip_hf_copy = [bool]$SkipHfCopy
    ollama_tags = @($OllamaTags)
    ollama_manifest_count = [int]$stats["manifest_count"]
    ollama_blob_count = [int]$stats["blob_count"]
    created_at = (Get-Date).ToString("s")
}
$report | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $PackRoot "PACK_REPORT.json") -Encoding UTF8

Write-Host ""
Write-Host ("[OK] Paket hazir: {0}" -f $PackRoot) -ForegroundColor Green
Write-Host ("[OK] Boyut: {0} GB" -f ([math]::Round($packBytes / 1GB, 3))) -ForegroundColor Green
Write-Host ("[OK] Ollama manifest: {0} | blob: {1}" -f $stats["manifest_count"], $stats["blob_count"]) -ForegroundColor Green
