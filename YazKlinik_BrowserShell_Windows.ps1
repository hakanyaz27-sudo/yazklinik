param(
  [string]$ServerUrl = "http://127.0.0.1:5052"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$server = [string]$ServerUrl
$server = $server.Trim().TrimEnd("/")
if (-not $server) { $server = "http://127.0.0.1:5052" }

$local = Join-Path $env:LOCALAPPDATA "YazKlinik"
$profile = Join-Path $local "BrowserShell"
$cache = Join-Path $local "BrowserShellCache"
New-Item -ItemType Directory -Force -Path $local, $profile | Out-Null
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $root "terminal_server_url.txt"), "$server`r`n", $utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path $local "terminal_server_url.txt"), "$server`r`n", $utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path $root "desktop_mode.txt"), "browser`r`n", $utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path $local "desktop_mode.txt"), "browser`r`n", $utf8NoBom)

$browserCandidates = @(
  (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
  (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
  (Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe"),
  (Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe")
) | Where-Object { $_ -and (Test-Path $_) }

if (-not $browserCandidates) {
  Write-Host "BROWSER_SHELL_NO_BROWSER"
  exit 2
}

$browser = $browserCandidates[0]
try {
  $ping = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Uri "$server/api/terminal/ping"
  if ($ping.StatusCode -ne 200) { Write-Host "BROWSER_SHELL_SERVER_WARN $($ping.StatusCode)" }
} catch {
  Write-Host "BROWSER_SHELL_SERVER_WARN"
}

Get-CimInstance Win32_Process | Where-Object {
  ($_.CommandLine -like "*WebShell\main.py*") -or
  ($_.CommandLine -like "*YazKlinik\BrowserShell*") -or
  ($_.CommandLine -like "*YazKlinik\BrowserShellTest*")
} | ForEach-Object {
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

$launchUrl = "$server/?yk_webshell=1"
$webshellUserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 YazKlinikWebShell/1.0"

$args = @(
  "--app=$launchUrl",
  "--user-data-dir=$profile",
  "--disk-cache-dir=$cache",
  "--disk-cache-size=536870912",
  "--media-cache-size=268435456",
  "--user-agent=$webshellUserAgent",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-extensions",
  "--disable-sync",
  "--disable-background-networking",
  "--disable-component-update",
  "--disable-domain-reliability",
  "--disable-notifications",
  "--disable-search-engine-choice-screen",
  "--disable-features=Translate,MediaRouter,CalculateNativeWinOcclusion",
  "--enable-gpu-rasterization",
  "--enable-zero-copy",
  "--enable-features=CanvasOopRasterization",
  "--enable-smooth-scrolling",
  "--disable-background-timer-throttling",
  "--disable-backgrounding-occluded-windows",
  "--disable-renderer-backgrounding",
  "--no-proxy-server"
)

$proc = Start-Process -FilePath $browser -ArgumentList $args -PassThru
Start-Sleep -Milliseconds 500
try {
  Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like "*YazKlinik\BrowserShell*"
  } | ForEach-Object {
    try {
      $p = Get-Process -Id $_.ProcessId -ErrorAction Stop
      $p.PriorityClass = "AboveNormal"
    } catch {}
  }
} catch {}
Write-Host "BROWSER_SHELL_STARTED pid=$($proc.Id) browser=$browser server=$server"
