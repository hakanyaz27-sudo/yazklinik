# =====================================================================
#  CLOUDFLARE_WORKER_KUR.ps1
#  cloudflare_bakim_worker.js Worker'ini Cloudflare'e yukler ve
#  yazhakan.com.tr/* + www.yazhakan.com.tr/* route'larina baglar.
#  (Free planda bakim sayfasi icin dogru yontem.)
#
#  Token nasil verilir:
#   A) Parametre  : .\CLOUDFLARE_WORKER_KUR.ps1 -Token "xxx"
#   B) Ortam deg. : $env:CF_API_TOKEN="xxx" ; .\CLOUDFLARE_WORKER_KUR.ps1
#   C) config.env: CF_API_TOKEN=xxx (opsiyonel)
#   D) Bos ise script guvenli sorar (gorunmez).
#
#  Gerekli token yetkileri (Create Custom Token):
#   - Account : Workers Scripts : Edit
#   - Zone    : Workers Routes  : Edit
#   - Zone    : Zone            : Read
#  Account Resources: hesabini sec. Zone Resources: yazhakan.com.tr.
# =====================================================================

[CmdletBinding()]
param(
  [string]$Token      = $env:CF_API_TOKEN,
  [string]$ZoneName   = "yazhakan.com.tr",
  [string]$ScriptName = "yazklinik-bakim",
  [string]$WorkerFile = (Join-Path $PSScriptRoot "cloudflare_bakim_worker.js"),
  [string[]]$Routes   = @("yazhakan.com.tr/*", "www.yazhakan.com.tr/*")
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

$auth = @{ Authorization = "Bearer $Token" }
$api  = "https://api.cloudflare.com/client/v4"

function Invoke-CFJson($Method, $Uri, $BodyObj) {
  try {
    if ($BodyObj) {
      return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $auth -ContentType 'application/json' -Body ($BodyObj | ConvertTo-Json -Depth 8)
    } else {
      return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $auth
    }
  } catch {
    $d = $_.ErrorDetails.Message
    if (-not $d -and $_.Exception.Response) { try { $d = (New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd() } catch {} }
    throw "API hatasi ($Method $Uri): $d"
  }
}

# --- 0) Worker dosyasini oku ---
if (-not (Test-Path -LiteralPath $WorkerFile)) { Write-Err "Worker dosyasi yok: $WorkerFile"; exit 1 }
$workerCode = Get-Content -LiteralPath $WorkerFile -Raw -Encoding UTF8
Write-Ok "Worker dosyasi okundu: $WorkerFile ($($workerCode.Length) bayt)"

# --- 1) Zone + Account ID bul ---
Write-Step "Zone/Account araniyor: $ZoneName"
$z = Invoke-CFJson "GET" "$api/zones?name=$ZoneName"
if (-not $z.success -or -not $z.result -or $z.result.Count -lt 1) {
  Write-Err "Zone bulunamadi. Token'da 'Zone:Read' var mi ve hesap dogru mu?"; exit 3
}
$ZoneId    = $z.result[0].id
$AccountId = $z.result[0].account.id
Write-Ok "Zone ID: $ZoneId"
Write-Ok "Account ID: $AccountId"

# --- 2) Worker script yukle (klasik format -> duz JS PUT) ---
Write-Step "Worker yukleniyor: $ScriptName"
$putUri = "$api/accounts/$AccountId/workers/scripts/$ScriptName"
try {
  $up = Invoke-RestMethod -Method Put -Uri $putUri -Headers $auth -ContentType 'application/javascript' -Body $workerCode
} catch {
  $d = $_.ErrorDetails.Message
  if (-not $d -and $_.Exception.Response) { try { $d = (New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd() } catch {} }
  Write-Err "Worker yuklenemedi: $d"
  Write-Err "Ipucu: Token'da 'Account > Workers Scripts > Edit' yetkisi gerekiyor."
  exit 4
}
if (-not $up.success) { Write-Err "Worker yuklenemedi: $($up.errors | ConvertTo-Json -Compress)"; exit 4 }
Write-Ok "Worker yuklendi."

# --- 3) Route'lari bagla (idempotent) ---
Write-Step "Route'lar baglaniyor"
$existing = @()
try {
  $r = Invoke-CFJson "GET" "$api/zones/$ZoneId/workers/routes"
  if ($r.success -and $r.result) { $existing = $r.result }
} catch { }

foreach ($pattern in $Routes) {
  $hit = $existing | Where-Object { $_.pattern -eq $pattern }
  if ($hit) {
    if ($hit.script -eq $ScriptName) {
      Write-Ok "Route zaten var: $pattern -> $ScriptName"
    } else {
      $upd = Invoke-CFJson "PUT" "$api/zones/$ZoneId/workers/routes/$($hit.id)" @{ pattern = $pattern; script = $ScriptName }
      if ($upd.success) { Write-Ok "Route guncellendi: $pattern -> $ScriptName" } else { Write-Err "Route guncellenemedi: $pattern" }
    }
  } else {
    $add = Invoke-CFJson "POST" "$api/zones/$ZoneId/workers/routes" @{ pattern = $pattern; script = $ScriptName }
    if ($add.success) { Write-Ok "Route eklendi: $pattern -> $ScriptName" } else { Write-Err "Route eklenemedi: $pattern -> $($add.errors | ConvertTo-Json -Compress)" }
  }
}

# --- 4) Dogrula ---
Write-Step "Dogrulama"
$rv = Invoke-CFJson "GET" "$api/zones/$ZoneId/workers/routes"
$mine = $rv.result | Where-Object { $_.script -eq $ScriptName }
foreach ($m in $mine) { Write-Host "    route: $($m.pattern) -> $($m.script)" -ForegroundColor Yellow }

if ($mine.Count -ge 1) {
  Write-Host "`n============================================================" -ForegroundColor Green
  Write-Host "  BASARILI: Worker yuklendi ve route'lara baglandi." -ForegroundColor Green
  Write-Host "  Artik sunucu (origin) cokunce yazhakan.com.tr acanlar" -ForegroundColor Green
  Write-Host "  'Sistem bakimda' sayfasini gorecek." -ForegroundColor Green
  Write-Host "  Test: D700 web surecini durdurup yazhakan.com.tr'yi ac." -ForegroundColor Green
  Write-Host "============================================================" -ForegroundColor Green
} else {
  Write-Err "Route dogrulanamadi. Cloudflare panelinden Workers Routes'a bak."
  exit 5
}
