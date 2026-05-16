param(
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Write-Step($Text) {
    Write-Host "[D300 TURBO] $Text" -ForegroundColor Cyan
}

function Set-UserEnv($Name, $Value) {
    [Environment]::SetEnvironmentVariable($Name, $Value, "User")
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    Write-Host "  $Name=$Value"
}

function Set-ConfigLine($Path, $Name, $Value) {
    if (-not (Test-Path $Path)) { return }
    $lines = [System.IO.File]::ReadAllLines($Path)
    if ($lines.Count -gt 0) {
        $lines[0] = $lines[0].TrimStart([char]0xFEFF)
    }
    $found = $false
    $out = foreach ($line in $lines) {
        if ($line -match "^\s*$([regex]::Escape($Name))=") {
            $found = $true
            "$Name=$Value"
        } else {
            $line
        }
    }
    if (-not $found) {
        $out += "$Name=$Value"
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($Path, [string[]]$out, $utf8NoBom)
}

Write-Step "Windows guc plani: Nihai Performans"
try {
    $ultimate = "e9a42b02-d5df-448d-aa00-03f14749eb61"
    $listed = powercfg /list
    $existing = ($listed | Select-String -Pattern "([0-9a-fA-F-]{36}).*(Nihai Performans|Ultimate Performance)" | Select-Object -First 1)
    if ($existing -and $existing.Line -match "([0-9a-fA-F-]{36})") {
        powercfg /setactive $matches[1] | Out-Null
    } else {
        $created = powercfg -duplicatescheme $ultimate 2>$null
        if ($LASTEXITCODE -eq 0 -and $created -match "([0-9a-fA-F-]{36})") {
            powercfg /setactive $matches[1] | Out-Null
        } else {
            powercfg /setactive $ultimate | Out-Null
        }
    }
} catch {
    powercfg /setactive SCHEME_MIN | Out-Null
}
powercfg /getactivescheme

Write-Step "Ollama kullanici ortami"
Set-UserEnv "OLLAMA_FLASH_ATTENTION" "1"
Set-UserEnv "OLLAMA_KV_CACHE_TYPE" "q8_0"
Set-UserEnv "OLLAMA_NUM_PARALLEL" "2"
Set-UserEnv "OLLAMA_MAX_LOADED_MODELS" "1"
Set-UserEnv "OLLAMA_KEEP_ALIVE" "8h"
Set-UserEnv "OLLAMA_LOAD_TIMEOUT" "10m"

Write-Step "config.env turbo satirlari"
$ConfigPath = Join-Path $Root "config.env"
$configMap = [ordered]@{
    "YAZKLINIK_WAITRESS_THREADS" = "64"
    "YAZKLINIK_SERVER_ENGINE" = "waitress"
    "YAZKLINIK_MEDIA_RAM_CACHE_GB" = "128"
    "YAZKLINIK_MEDIA_RAM_CACHE_MAX_FILE_MB" = "2048"
    "YAZKLINIK_RAM_RESERVE_GB" = "16"
    "YAZKLINIK_PROGRAM_RAM_CACHE_MB" = "16384"
    "YAZKLINIK_DB_CACHE_MB" = "256"
    "YAZKLINIK_DB_MMAP_GB" = "2"
    "YAZKLINIK_GPU_PROFILE" = "rtx5090"
    "YAZKLINIK_AI_PROVIDER" = "ollama"
    "YAZKLINIK_OLLAMA_MODEL" = "qwen2.5:32b"
    "YAZKLINIK_OLLAMA_CTX_LIMIT" = "8192"
    "YAZKLINIK_OLLAMA_NUM_BATCH" = "2048"
    "YAZKLINIK_OLLAMA_NUM_GPU" = "99"
    "YAZKLINIK_OLLAMA_NUM_PARALLEL" = "2"
    "YAZKLINIK_OLLAMA_KEEP_ALIVE" = "8h"
    "YAZKLINIK_OLLAMA_FLASH_ATTENTION" = "1"
    "YAZKLINIK_OLLAMA_KV_CACHE_TYPE" = "q8_0"
    "YAZKLINIK_OLLAMA_MAX_LOADED_MODELS" = "1"
    "YAZKLINIK_OLLAMA_NUM_THREAD" = "16"
    "YAZKLINIK_ALEX_PREWARM" = "1"
    "YAZKLINIK_WHISPER_DEVICE" = "cuda"
    "YAZKLINIK_WHISPER_COMPUTE_TYPE" = "float16"
    "YAZKLINIK_XTTS_DEVICE" = "cuda"
}
foreach ($item in $configMap.GetEnumerator()) {
    Set-ConfigLine $ConfigPath $item.Key $item.Value
}

Write-Step "SQLite settings turbo profili"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }
$code = @"
import datetime, os, sqlite3
root = r"$Root"
db_path = os.environ.get("YAZKLINIK_DB_PATH") or os.path.join(root, "local_db", "yazklinik_v68.sqlite3")
settings = {
 "sysparam_waitress_threads":"64",
 "sysparam_ai_provider":"ollama",
 "sysparam_ollama_model":"qwen2.5:32b",
 "sysparam_ollama_task_dialog_model":"qwen2.5:32b",
 "sysparam_ollama_task_phone_model":"qwen2.5:32b",
 "sysparam_ollama_task_fast_model":"llama3.1:8b",
 "sysparam_ollama_task_general_model":"qwen2.5:32b",
 "sysparam_ollama_task_clinical_model":"qwen2.5:32b",
 "sysparam_ollama_task_summary_model":"qwen2.5:32b",
 "sysparam_ollama_ctx_limit":"8192",
 "sysparam_ollama_num_batch":"2048",
 "sysparam_ollama_num_gpu":"99",
 "sysparam_ollama_num_parallel":"2",
 "sysparam_ollama_keep_alive":"8h",
 "sysparam_whisper_device":"cuda",
 "sysparam_whisper_compute_type":"float16",
 "sysparam_xtts_device":"cuda",
 "sysparam_media_ram_cache_gb":"128",
 "sysparam_media_ram_cache_max_file_mb":"2048",
 "sysparam_ram_reserve_gb":"16",
 "sysparam_program_ram_cache_mb":"16384",
 "sysparam_program_ram_cache_prewarm":"1",
 "sysparam_db_cache_mb":"256",
 "sysparam_db_mmap_gb":"2",
 "sysparam_webshell_cache_mb":"4096",
 "sysparam_webshell_gpu_turbo":"1",
}
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
con = sqlite3.connect(db_path)
con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
cols = {r[1] for r in con.execute("PRAGMA table_info(settings)")}
if "updated_at" in cols:
    for k, v in settings.items():
        con.execute("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at", (k, v, now))
else:
    for k, v in settings.items():
        con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
con.commit()
con.close()
print("DB settings OK:", db_path)
"@
$code | & $Py -

if (-not $NoRestart) {
    Write-Step "Ollama restart + qwen2.5:32b prewarm"
    Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    $Ollama = (Get-Command ollama.exe -ErrorAction SilentlyContinue).Source
    if (-not $Ollama) { $Ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" }
    Start-Process -FilePath $Ollama -ArgumentList @("serve") -WindowStyle Hidden -WorkingDirectory $Root
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        $code = curl.exe -s -o NUL --connect-timeout 2 --max-time 4 -w "%{http_code}" http://127.0.0.1:11434/api/tags
        if ($code -eq "200") { break }
    }
    $warm = '{"model":"qwen2.5:32b","prompt":"Tek kelimeyle hazir de.","stream":false,"keep_alive":"8h","options":{"temperature":0.2,"num_predict":24,"num_ctx":3072,"num_batch":2048,"num_gpu":99}}'
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/generate" -Method Post -ContentType "application/json" -Body $warm | Out-Null
    ollama ps
}

Write-Step "Tamam"
