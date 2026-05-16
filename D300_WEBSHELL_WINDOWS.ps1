param(
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$PreferredWebShell = Join-Path $Root "YazKlinik_WebShell_Windows.bat"
if (Test-Path $PreferredWebShell) {
    & $PreferredWebShell
    return
}

$ConfigPath = Join-Path $Root "config.env"
if (Test-Path $ConfigPath) {
    Get-Content $ConfigPath | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $name, $value = $line.Split("=", 2)
            [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), "Process")
        }
    }
}

if (-not $env:YAZKLINIK_NAS_ROOT) { $env:YAZKLINIK_NAS_ROOT = "\\asustor\Voluson" }
if (-not $env:YAZKLINIK_DB_PATH) { $env:YAZKLINIK_DB_PATH = Join-Path $Root "local_db\yazklinik_v68.sqlite3" }
if (-not $env:YAZKLINIK_WEB_PORT) { $env:YAZKLINIK_WEB_PORT = "5052" }
if (-not $env:YAZKLINIK_HTTPS_PORT) { $env:YAZKLINIK_HTTPS_PORT = "5443" }

$ServerUrl = "http://127.0.0.1:$($env:YAZKLINIK_WEB_PORT)"
$env:YAZKLINIK_SERVER_URL = $ServerUrl
$env:YAZKLINIK_WEB_URL = $ServerUrl
$env:YAZKLINIK_AI_SERVER_URL = $ServerUrl
$env:YAZKLINIK_DEFAULT_SERVER_URL = $ServerUrl
$env:YAZKLINIK_ALLOW_LOCAL_TERMINAL_SERVER = "1"
$env:YAZKLINIK_DESKTOP_MODE = "shell"
$env:YAZKLINIK_DESKTOP_MODE_FORCE = "1"
$env:YAZKLINIK_DESKTOP_WEB_SHELL = "1"
$env:YAZKLINIK_DESKTOP_ENABLE_WEBENGINE = "1"
$env:YAZKLINIK_DESKTOP_DISABLE_WEBENGINE = "0"
$env:YAZKLINIK_DESKTOP_WEB_MIRROR = "0"
$env:YAZKLINIK_DESKTOP_WEB_CENTER_FIRST = "1"
$env:YAZKLINIK_DESKTOP_LEAN_SHELL = "1"
if (-not $env:YAZKLINIK_TERMINAL_TOKEN) { $env:YAZKLINIK_TERMINAL_TOKEN = [guid]::NewGuid().ToString("N") }
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

$Python = "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = Join-Path $Root ".venv\Scripts\python.exe" }
if (-not (Test-Path $Python)) { $Python = "python" }

& $Python (Join-Path $Root "D300_TERMINAL_SYNC.py") --server-url $ServerUrl | Out-Null
if (Test-Path (Join-Path $Root "terminal_env.ps1")) {
    . (Join-Path $Root "terminal_env.ps1")
}
$env:YAZKLINIK_DESKTOP_MODE = "shell"
$env:YAZKLINIK_DESKTOP_MODE_FORCE = "1"
$env:YAZKLINIK_DESKTOP_WEB_SHELL = "1"
$env:YAZKLINIK_DESKTOP_ENABLE_WEBENGINE = "1"
$env:YAZKLINIK_DESKTOP_DISABLE_WEBENGINE = "0"
$env:YAZKLINIK_DESKTOP_WEB_MIRROR = "0"
$env:YAZKLINIK_DESKTOP_WEB_CENTER_FIRST = "1"
$env:YAZKLINIK_DESKTOP_LEAN_SHELL = "1"

function Test-YazKlinikReady {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri "$Url/giris" -UseBasicParsing -TimeoutSec 2
        return ($response.StatusCode -eq 200)
    } catch {
        return $false
    }
}

if (-not (Test-YazKlinikReady -Url $ServerUrl)) {
    $Port = [int]$env:YAZKLINIK_WEB_PORT
    $oldPids = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object State -eq "Listen" |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($pidValue in $oldPids) {
        Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    if (-not (Test-Path (Join-Path $Root "local_db"))) { New-Item -ItemType Directory -Path (Join-Path $Root "local_db") | Out-Null }
    if (-not (Test-Path (Join-Path $Root "auto_backups"))) { New-Item -ItemType Directory -Path (Join-Path $Root "auto_backups") | Out-Null }
    Start-Process -FilePath $Python `
        -ArgumentList @("-u", "yazklinik_web.py") `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Root "D300_server.log") `
        -RedirectStandardError (Join-Path $Root "D300_server_HATA.log")

    $ready = $false
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 1
        if (Test-YazKlinikReady -Url $ServerUrl) {
            $ready = $true
            break
        }
    }
    if (-not $ready) {
        Write-Host "D200 server acilmadi. D300_server_HATA.log dosyasina bakin."
        if (-not $NoPause) { Read-Host "Kapatmak icin Enter" | Out-Null }
        exit 2
    }
}

$DesktopScript = Join-Path $Root "yazklinik_desktop_v1000.py"
$GuiPython = $Python
try {
    $candidate = Join-Path (Split-Path -Parent $Python) "pythonw.exe"
    if (Test-Path $candidate) { $GuiPython = $candidate }
} catch {
}

Start-Process -FilePath $GuiPython `
    -ArgumentList @("-X", "utf8", $DesktopScript) `
    -WorkingDirectory $Root

Write-Host "YazKlinik WebShell acildi: menulu web arayuz ($ServerUrl)"
if (-not $NoPause) {
    Read-Host "Kapatmak icin Enter" | Out-Null
}

