$ErrorActionPreference = "SilentlyContinue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

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
if (-not $env:YAZKLINIK_ENABLE_HTTPS) { $env:YAZKLINIK_ENABLE_HTTPS = "1" }
$ServerUrl = if ($env:YAZKLINIK_ENABLE_HTTPS -in @("1","true","True","on","ON")) {
    "https://192.168.1.50:$($env:YAZKLINIK_HTTPS_PORT)"
} else {
    "http://192.168.1.50:$($env:YAZKLINIK_WEB_PORT)"
}
$env:YAZKLINIK_SERVER_URL = $ServerUrl
$env:YAZKLINIK_WEB_URL = $ServerUrl
$env:YAZKLINIK_AI_SERVER_URL = $ServerUrl
$env:YAZKLINIK_DEFAULT_SERVER_URL = $ServerUrl
$env:YAZKLINIK_ALLOW_LOCAL_TERMINAL_SERVER = "1"
if (-not $env:YAZKLINIK_TERMINAL_TOKEN) { $env:YAZKLINIK_TERMINAL_TOKEN = [guid]::NewGuid().ToString("N") }
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

if (-not $env:YAZKLINIK_RTX5090_STARTUP_PROFILE) { $env:YAZKLINIK_RTX5090_STARTUP_PROFILE = "1" }
if ($env:YAZKLINIK_RTX5090_STARTUP_PROFILE -notin @("0", "false", "False", "off", "OFF")) {
    if (-not $env:OLLAMA_CONTEXT_LENGTH) {
        if ($env:YAZKLINIK_OLLAMA_CTX_LIMIT) { $env:OLLAMA_CONTEXT_LENGTH = "$($env:YAZKLINIK_OLLAMA_CTX_LIMIT)" }
        else { $env:OLLAMA_CONTEXT_LENGTH = "8192" }
    }
    if (-not $env:OLLAMA_NUM_PARALLEL) {
        if ($env:YAZKLINIK_OLLAMA_NUM_PARALLEL) { $env:OLLAMA_NUM_PARALLEL = "$($env:YAZKLINIK_OLLAMA_NUM_PARALLEL)" }
        else { $env:OLLAMA_NUM_PARALLEL = "1" }
    }
    if (-not $env:OLLAMA_MAX_QUEUE) {
        if ($env:YAZKLINIK_OLLAMA_MAX_QUEUE) { $env:OLLAMA_MAX_QUEUE = "$($env:YAZKLINIK_OLLAMA_MAX_QUEUE)" }
        else { $env:OLLAMA_MAX_QUEUE = "256" }
    }
    if (-not $env:PYTORCH_CUDA_ALLOC_CONF) { $env:PYTORCH_CUDA_ALLOC_CONF = "backend:cudaMallocAsync" }
    if (-not $env:PYTORCH_ALLOC_CONF) { $env:PYTORCH_ALLOC_CONF = $env:PYTORCH_CUDA_ALLOC_CONF }

    if (-not $env:YAZKLINIK_POWER_PLAN_STARTUP) { $env:YAZKLINIK_POWER_PLAN_STARTUP = "1" }
    if ($env:YAZKLINIK_POWER_PLAN_STARTUP -notin @("0", "false", "False", "off", "OFF")) {
        try {
            $dup = powercfg -duplicatescheme "e9a42b02-d5df-448d-aa00-03f14749eb61" 2>&1
            $guid = [regex]::Match(($dup -join "`n"), "[0-9a-fA-F-]{36}").Value
            if (-not $guid) {
                $line = powercfg /list | Select-String -Pattern "Nihai Performans|Ultimate Performance|High performance|Yuksek performans" | Select-Object -First 1
                if ($line) { $guid = [regex]::Match($line.Line, "[0-9a-fA-F-]{36}").Value }
            }
            if ($guid) { powercfg /setactive $guid | Out-Null }
        } catch {
        }
    }
}

$Python = "$PSScriptRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = Join-Path $Root ".venv\Scripts\python.exe"
}
if (-not (Test-Path $Python)) {
    exit 1
}

& $Python (Join-Path $Root "D700_TERMINAL_SYNC.py") --server-url $ServerUrl | Out-Null
. (Join-Path $Root "terminal_env.ps1")

$Port = [int]$env:YAZKLINIK_WEB_PORT
$OldPids = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object State -eq "Listen" |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($PidValue in $OldPids) {
    Stop-Process -Id $PidValue -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

if (-not (Test-Path (Join-Path $Root "local_db"))) { New-Item -ItemType Directory -Path (Join-Path $Root "local_db") | Out-Null }
if (-not (Test-Path (Join-Path $Root "auto_backups"))) { New-Item -ItemType Directory -Path (Join-Path $Root "auto_backups") | Out-Null }

$Stdout = Join-Path $Root "D700_server.log"
$Stderr = Join-Path $Root "D700_server_HATA.log"
Start-Process -FilePath $Python `
    -ArgumentList @("-u", "yazklinik_web.py") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $Stdout `
    -RedirectStandardError $Stderr

$Url = $ServerUrl
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri "$Url/giris" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            Start-Process $Url
            exit 0
        }
    } catch {
    }
}

exit 2




