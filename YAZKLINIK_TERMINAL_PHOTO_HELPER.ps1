param([string]$RawUrl)

$ErrorActionPreference = 'SilentlyContinue'

function Decode-Url {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return '' }
    return [Uri]::UnescapeDataString(($Value -replace '\+', ' '))
}

function Get-QueryMap {
    param([string]$Url)
    $map = @{}
    try { $u = [Uri]$Url } catch { return $map }
    $q = $u.Query.TrimStart('?')
    foreach ($part in ($q -split '&')) {
        if ([string]::IsNullOrWhiteSpace($part)) { continue }
        $kv = $part -split '=', 2
        $k = Decode-Url $kv[0]
        $v = if ($kv.Count -gt 1) { Decode-Url $kv[1] } else { '' }
        if ($k) { $map[$k] = $v }
    }
    return $map
}

function Download-Image {
    param([string]$Url)
    if ([string]::IsNullOrWhiteSpace($Url) -or $Url -notmatch '^https?://') { return $null }
    try {
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
        $name = [IO.Path]::GetFileName(([Uri]$Url).AbsolutePath)
        if ([string]::IsNullOrWhiteSpace($name)) { $name = 'yazklinik-photo.jpg' }
        $ext = [IO.Path]::GetExtension($name)
        if ([string]::IsNullOrWhiteSpace($ext)) { $ext = '.jpg' }
        $dest = Join-Path $env:TEMP ('YazKlinikPhoto_' + [DateTime]::Now.ToString('yyyyMMdd_HHmmss_fff') + $ext)
        Invoke-WebRequest -Uri $Url -OutFile $dest -UseBasicParsing -TimeoutSec 60
        if (Test-Path -LiteralPath $dest) { return $dest }
    } catch {}
    return $null
}

$params = Get-QueryMap $RawUrl

$path = $params['file']
if ([string]::IsNullOrWhiteSpace($path)) { $path = $params['path'] }
if (-not [string]::IsNullOrWhiteSpace($path) -and (Test-Path -LiteralPath $path)) {
    Start-Process -FilePath $path
    exit 0
}

$src = $params['src']
if ([string]::IsNullOrWhiteSpace($src)) { $src = $params['url'] }
$downloaded = Download-Image $src
if ($downloaded -and (Test-Path -LiteralPath $downloaded)) {
    Start-Process -FilePath $downloaded
    exit 0
}

exit 1
