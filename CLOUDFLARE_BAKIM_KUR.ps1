# =====================================================================
#  CLOUDFLARE_BAKIM_KUR.ps1
#  YazKlinik 5xx "Sistem bakimda" ozel hata sayfasini Cloudflare'e baglar.
#
#  Ne yapar:
#   1) https://yazhakan.com.tr/bakim erisilebilir + zorunlu CF token var mi dogrular
#   2) Cloudflare'de yazhakan.com.tr zone_id'sini bulur
#   3) "500 class errors" ozel hata sayfasini /bakim URL'sine ayarlar
#   4) Geri okuyup dogrular
#
#  Token nasil verilir (3 yol):
#   A) Parametre  : .\CLOUDFLARE_BAKIM_KUR.ps1 -Token "cf_xxx"
#   B) Ortam degiskeni: $env:CF_API_TOKEN = "cf_xxx" ; .\CLOUDFLARE_BAKIM_KUR.ps1
#   C) config.env: CF_API_TOKEN=cf_xxx (opsiyonel)
#   D) Hicbiri yoksa script guvenli sekilde sorar (ekranda gorunmez)
#
#  Gerekli token yetkileri (Cloudflare > My Profile > API Tokens):
#   - Zone : Zone        : Read      (zone'u isimle bulmak icin)
#   - Zone : Custom Pages : Edit      (sayfayi ayarlamak icin)
#   Kapsam: sadece yazhakan.com.tr zone'u yeterli.
# =====================================================================

[CmdletBinding()]
param(
  [string]$Token = $env:CF_API_TOKEN,
  [string]$ZoneId = $env:CF_ZONE_ID,
  [string]$ZoneName = "yazhakan.com.tr",
  [string]$PageUrl = "https://yazhakan.com.tr/bakim"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Write-Step($m) { Write-Host "`n[+] $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "    OK  - $m" -ForegroundColor Green }
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

# --- Token al ---
if (-not $Token) { $Token = Get-ConfigEnvValue -Key "CF_API_TOKEN" }
if (-not $Token) { $Token = Get-ConfigEnvValue -Key "CLOUDFLARE_API_TOKEN" }
if (-not $Token) {
  $sec = Read-Host "Cloudflare API Token (ekranda gorunmez)" -AsSecureString
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
  try   { $Token = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}
$Token = ($Token | Out-String).Trim()
if (-not $Token) { Write-Err "Token bos. Cikiliyor."; exit 1 }

$headers = @{ "Authorization" = "Bearer $Token"; "Content-Type" = "application/json" }

function Invoke-CF($Method, $Uri, $BodyObj) {
  try {
    if ($BodyObj) {
      return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers -Body ($BodyObj | ConvertTo-Json -Depth 6)
    } else {
      return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers
    }
  } catch {
    $detail = $_.ErrorDetails.Message
    if (-not $detail -and $_.Exception.Response) {
      try {
        $rs = New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())
        $detail = $rs.ReadToEnd()
      } catch {}
    }
    throw "Cloudflare API cagrisi basarisiz ($Method $Uri): $detail"
  }
}

# --- 1) Bakim sayfasi erisilebilir + token var mi ---
Write-Step "Bakim sayfasi kontrol ediliyor: $PageUrl"
try {
  $resp = Invoke-WebRequest -Uri $PageUrl -UseBasicParsing -TimeoutSec 15
  if ($resp.StatusCode -ne 200) { Write-Err "Sayfa HTTP $($resp.StatusCode) dondu (200 bekleniyordu). Sunucu acik mi?"; exit 2 }
  if ($resp.Content -notmatch [regex]::Escape("::CLOUDFLARE_ERROR_500S_BOX::")) {
    Write-Err "Sayfada zorunlu '::CLOUDFLARE_ERROR_500S_BOX::' token'i yok. Cloudflare reddeder."; exit 2
  }
  Write-Ok "Sayfa 200 dondu ve zorunlu token mevcut."
} catch {
  Write-Err "Bakim sayfasina ulasilamadi. Sunucu/tunel acik mi? Ayrinti: $($_.Exception.Message)"
  exit 2
}

# --- 2) Zone ID bul ---
if (-not $ZoneId) {
  Write-Step "Zone ID araniyor: $ZoneName"
  $z = Invoke-CF "GET" "https://api.cloudflare.com/client/v4/zones?name=$ZoneName"
  if (-not $z.success) { Write-Err "Zone listesi alinamadi: $($z.errors | ConvertTo-Json -Compress)"; exit 3 }
  if (-not $z.result -or $z.result.Count -lt 1) { Write-Err "'$ZoneName' bu hesapta bulunamadi. Token dogru hesapta mi?"; exit 3 }
  $ZoneId = $z.result[0].id
}
Write-Ok "Zone ID: $ZoneId"

# --- 3) 500-class ozel hata sayfasini ayarla ---
Write-Step "5xx ozel hata sayfasi ayarlaniyor -> $PageUrl"
$body = @{ url = $PageUrl; state = "customized" }
$put = Invoke-CF "PUT" "https://api.cloudflare.com/client/v4/zones/$ZoneId/custom_pages/500_errors" $body
if (-not $put.success) { Write-Err "Ayarlanamadi: $($put.errors | ConvertTo-Json -Compress)"; exit 4 }
Write-Ok "Cloudflare istegi kabul etti."

# --- 4) Geri oku / dogrula ---
Write-Step "Dogrulama (geri okuma)"
$chk = Invoke-CF "GET" "https://api.cloudflare.com/client/v4/zones/$ZoneId/custom_pages/500_errors"
$state = $chk.result.state
$url   = $chk.result.url
Write-Host "    state = $state" -ForegroundColor Yellow
Write-Host "    url   = $url"   -ForegroundColor Yellow
if ($state -eq "customized") {
  Write-Host "`n============================================================" -ForegroundColor Green
  Write-Host "  BASARILI: Artik origin 5xx verdiginde Cloudflare" -ForegroundColor Green
  Write-Host "  '$PageUrl' bakim sayfasini gosterecek." -ForegroundColor Green
  Write-Host "  Test: sunucuyu kapatip yazhakan.com.tr'yi ac." -ForegroundColor Green
  Write-Host "============================================================" -ForegroundColor Green
} else {
  Write-Err "Beklenmedik durum: state=$state. Panelden kontrol edin."
  exit 5
}
