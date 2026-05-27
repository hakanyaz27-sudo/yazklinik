[CmdletBinding()]
param(
  [string]$Token = $env:CF_API_TOKEN,
  [string]$ZoneId = $env:CF_ZONE_ID,
  [switch]$SkipCustomPage
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Write-Step($m) { Write-Host "`n[+] $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "    OK  - $m" -ForegroundColor Green }
function Write-Warn2($m){ Write-Host "    UYARI - $m" -ForegroundColor Yellow }
function Write-Err($m)  { Write-Host "    HATA - $m" -ForegroundColor Red }

function Get-ConfigEnvValue {
  param([string]$Key)
  try {
    $cfg = Join-Path $PSScriptRoot "config.env"
    if (-not (Test-Path -LiteralPath $cfg)) { return $null }
    $line = Get-Content -LiteralPath $cfg -Encoding UTF8 |
      Where-Object { $_ -match "^\s*$([regex]::Escape($Key))\s*=" } |
      Select-Object -First 1
    if (-not $line) { return $null }
    return (($line -split "=", 2)[1].Trim())
  } catch {
    return $null
  }
}

if (-not $Token) { $Token = Get-ConfigEnvValue -Key "CF_API_TOKEN" }
if (-not $Token) { $Token = Get-ConfigEnvValue -Key "CLOUDFLARE_API_TOKEN" }
if (-not $ZoneId) { $ZoneId = Get-ConfigEnvValue -Key "CF_ZONE_ID" }
if (-not $Token) {
  Write-Warn2 "Cloudflare token bulunamadi; guvenli giris istenecek."
  $sec = Read-Host "Cloudflare API Token (ekranda gorunmez)" -AsSecureString
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
  try   { $Token = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}
$Token = ($Token | Out-String).Trim()

$workerScript = Join-Path $PSScriptRoot "CLOUDFLARE_WORKER_KUR.ps1"
$customPageScript = Join-Path $PSScriptRoot "CLOUDFLARE_BAKIM_KUR.ps1"

if (-not (Test-Path -LiteralPath $workerScript)) {
  Write-Err "Bulunamadi: $workerScript"
  exit 2
}
if (-not (Test-Path -LiteralPath $customPageScript)) {
  Write-Err "Bulunamadi: $customPageScript"
  exit 2
}
if (-not $Token) {
  Write-Err "Cloudflare token bos. Worker deploy atlandi."
  Write-Host "    Tekrar calistirirken token girin veya config.env icine CF_API_TOKEN=... ekleyin." -ForegroundColor Yellow
  exit 3
}

Write-Step "Cloudflare Worker deploy + route baglama"
try {
  & $workerScript -Token $Token
} catch {
  Write-Err "Worker adimi exception verdi: $($_.Exception.Message)"
  exit 4
}
if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
  Write-Err "Worker adimi basarisiz. ExitCode=$LASTEXITCODE"
  exit 4
}
Write-Ok "Worker/route adimi tamam."

if ($SkipCustomPage) {
  Write-Warn2 "Custom page adimi atlandi (SkipCustomPage)."
  Write-Host "`nCLOUDFLARE_FULL_SETUP_OK" -ForegroundColor Green
  exit 0
}

Write-Step "Cloudflare 500 custom page adimi (opsiyonel)"
try {
  if ($ZoneId) {
    & $customPageScript -Token $Token -ZoneId $ZoneId
  } else {
    & $customPageScript -Token $Token
  }
  if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    throw "ExitCode=$LASTEXITCODE"
  }
  Write-Ok "Custom page adimi tamam."
} catch {
  $msg = $_.Exception.Message
  Write-Warn2 "Custom page adimi tamamlanamadi: $msg"
  Write-Warn2 "Free plan'da 5xx custom page kapali olabilir; Worker route aktif kalir."
}

Write-Host "`nCLOUDFLARE_FULL_SETUP_OK" -ForegroundColor Green
exit 0
