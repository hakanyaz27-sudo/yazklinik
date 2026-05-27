param(
  [switch]$Silent
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $env:USERPROFILE '.cloudflared\config.yml'
$RuntimeDir = Join-Path $Root 'runtime_state\cloudflared'
$StdoutLog = Join-Path $RuntimeDir 'cloudflared.stdout.log'
$StderrLog = Join-Path $RuntimeDir 'cloudflared.stderr.log'

if (-not (Test-Path -LiteralPath $ConfigPath)) {
  if (-not $Silent) { Write-Host ('[cloudflared] config yok: ' + $ConfigPath) }
  exit 0
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

$existing = Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -and $_.CommandLine.Contains('tunnel') -and $_.CommandLine.Contains('run') } |
  Select-Object -First 1

if ($existing) {
  if (-not $Silent) { Write-Host ('[cloudflared] zaten calisiyor PID=' + $existing.ProcessId) }
  exit 0
}

$cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cmd -or -not $cmd.Source) {
  throw 'cloudflared komutu bulunamadi. once kur: winget install Cloudflare.cloudflared'
}

$proc = Start-Process `
  -FilePath $cmd.Source `
  -ArgumentList @('--config', $ConfigPath, 'tunnel', 'run') `
  -WindowStyle Hidden `
  -RedirectStandardOutput $StdoutLog `
  -RedirectStandardError $StderrLog `
  -PassThru

Start-Sleep -Seconds 4

$up = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
if (-not $up) {
  $tail = ''
  if (Test-Path -LiteralPath $StderrLog) {
    $tail = (Get-Content -LiteralPath $StderrLog -Tail 20 | Out-String)
  }
  throw ('cloudflared basladi ama hemen kapandi. stderr: ' + $tail)
}

if (-not $Silent) { Write-Host ('[cloudflared] baslatildi PID=' + $proc.Id) }
