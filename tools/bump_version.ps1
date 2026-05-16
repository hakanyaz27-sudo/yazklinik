param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^D\d+$")]
    [string]$VersionCode,

    [string]$Date = (Get-Date -Format "yyyy-MM-dd")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Update-RegexInFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [Parameter(Mandatory = $true)][string]$Replacement,
        [switch]$RequireChange
    )

    $raw = Get-Content -Path $Path -Raw -Encoding UTF8
    $matched = [Regex]::IsMatch($raw, $Pattern)
    if ($RequireChange -and -not $matched) {
        throw "Beklenen satir bulunamadi: $Path"
    }
    $updated = [Regex]::Replace($raw, $Pattern, $Replacement)
    if ($updated -ne $raw) {
        Set-Content -Path $Path -Value $updated -Encoding UTF8
        Write-Host "Guncellendi: $Path"
    }
    else {
        Write-Host "Degisiklik yok: $Path"
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$edition = "Final $VersionCode"
$appVersion = "YazKlinik Final $VersionCode"
$webShellVersion = "YazKlinik WebShell v3.0 - Final $VersionCode"

$webPy = Join-Path $repoRoot "yazklinik_web.py"
$v68Py = Join-Path $repoRoot "yazklinik_v68.py"
$webShellMain = Join-Path $repoRoot "WebShell\\main.py"
$versionJson = Join-Path $repoRoot "VERSION.json"

Update-RegexInFile -Path $webPy `
    -Pattern '(?m)^(PRODUCT_EDITION\s*=\s*")Final D\d+(")$' `
    -Replacement ('${1}' + $edition + '${2}') `
    -RequireChange

Update-RegexInFile -Path $v68Py `
    -Pattern '(?m)^(APP_VERSION\s*=\s*")YazKlinik Final D\d+(")$' `
    -Replacement ('${1}' + $appVersion + '${2}') `
    -RequireChange

Update-RegexInFile -Path $webShellMain `
    -Pattern '(?m)^(APP_VERSION\s*=\s*")YazKlinik WebShell v3\.0 - Final D\d+(")$' `
    -Replacement ('${1}' + $webShellVersion + '${2}') `
    -RequireChange

Update-RegexInFile -Path $versionJson `
    -Pattern '(?m)^(\s*"version"\s*:\s*")YazKlinik Final D\d+(")' `
    -Replacement ('${1}' + $appVersion + '${2}') `
    -RequireChange

Update-RegexInFile -Path $versionJson `
    -Pattern '(?m)^(\s*"version_code"\s*:\s*")D\d+(")' `
    -Replacement ('${1}' + $VersionCode + '${2}') `
    -RequireChange

Update-RegexInFile -Path $versionJson `
    -Pattern '(?m)^(\s*"date"\s*:\s*")\d{4}-\d{2}-\d{2}(")' `
    -Replacement ('${1}' + $Date + '${2}') `
    -RequireChange

Write-Host "Tamamlandi -> $VersionCode ($Date)"
