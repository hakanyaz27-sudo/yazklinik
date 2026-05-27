param(
  [switch]$Quiet,
  [switch]$StopRisky,
  [switch]$RepairConfig,
  [switch]$StrictManagedOwnerOff,
  [switch]$PersistManagedOwnerOff,
  [switch]$RepairPortal,
  [switch]$RequirePortal,
  [int]$RiskMinAgeSec = 120
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Config = Join-Path $Root "config.env"
$HealthLog = Join-Path $Root "D700_health_monitor.log"
$FailCount = 0
$ExcludedPids = @($PID)
try {
  $cursor = Get-CimInstance Win32_Process -Filter "ProcessId=$PID"
  for ($i = 0; $i -lt 6 -and $cursor -and $cursor.ParentProcessId; $i++) {
    $ExcludedPids += [int]$cursor.ParentProcessId
    $cursor = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f [int]$cursor.ParentProcessId) -ErrorAction SilentlyContinue
  }
} catch {}

function Write-Check {
  param([string]$Name, [bool]$Ok, [string]$Detail = "")
  if (-not $Ok) { $script:FailCount += 1 }
  $tag = if ($Ok) { "OK" } else { "FAIL" }
  $line = "[{0}] {1}" -f $tag, $Name
  if ($Detail) { $line += " - $Detail" }
  if (-not $Quiet) { Write-Host $line }
}

function Test-Http {
  param(
    [string]$Name,
    [string]$Url,
    [switch]$Insecure,
    [int]$TimeoutSec = 8
  )
  $args = @("-s", "--max-time", "$TimeoutSec", "-o", "NUL", "-w", "%{http_code} %{time_total}")
  if ($Insecure) { $args = @("-k") + $args }
  $args += $Url
  try {
    $raw = (& curl.exe @args 2>$null).Trim()
    $code = ($raw -split "\s+")[0]
    Write-Check $Name ($code -eq "200") "$raw $Url"
  } catch {
    Write-Check $Name $false $_.Exception.Message
  }
}

function Test-HttpBootAware {
  param(
    [string]$Name,
    [string]$Url,
    [switch]$Insecure,
    [int]$TimeoutSec = 8,
    [bool]$BootGraceActive = $false,
    [string]$BootGraceNote = ""
  )
  $args = @("-s", "--max-time", "$TimeoutSec", "-o", "NUL", "-w", "%{http_code} %{time_total}")
  if ($Insecure) { $args = @("-k") + $args }
  $args += $Url
  try {
    $raw = (& curl.exe @args 2>$null).Trim()
    $code = ($raw -split "\s+")[0]
    if ($code -eq "200") {
      Write-Check $Name $true "$raw $Url"
      return
    }
    if ($BootGraceActive) {
      $detail = "$raw $Url"
      if ($BootGraceNote) { $detail += " | $BootGraceNote" }
      if (-not $Quiet) { Write-Host ("[WARN] {0} - {1}" -f $Name, $detail) }
      return
    }
    Write-Check $Name $false "$raw $Url"
  } catch {
    if ($BootGraceActive) {
      $detail = $_.Exception.Message
      if ($BootGraceNote) { $detail += " | $BootGraceNote" }
      if (-not $Quiet) { Write-Host ("[WARN] {0} - {1}" -f $Name, $detail) }
      return
    }
    Write-Check $Name $false $_.Exception.Message
  }
}

function Test-HttpOptional {
  param(
    [string]$Name,
    [string]$Url,
    [switch]$Insecure,
    [int]$TimeoutSec = 8
  )
  $args = @("-s", "--max-time", "$TimeoutSec", "-o", "NUL", "-w", "%{http_code} %{time_total}")
  if ($Insecure) { $args = @("-k") + $args }
  $args += $Url
  try {
    $raw = (& curl.exe @args 2>$null).Trim()
    $code = ($raw -split "\s+")[0]
    $ok = ($code -eq "200")
    $tag = if ($ok) { "OK" } else { "WARN" }
    if (-not $Quiet) { Write-Host ("[{0}] {1} - {2} {3}" -f $tag, $Name, $raw, $Url) }
  } catch {
    if (-not $Quiet) { Write-Host ("[WARN] {0} - {1}" -f $Name, $_.Exception.Message) }
  }
}

function Get-ConfigIntValue {
  param(
    [string[]]$Lines,
    [string]$Key,
    [int]$Default
  )
  if (-not $Lines -or $Lines.Count -eq 0) { return $Default }
  $line = ($Lines | Where-Object { $_ -match ("^" + [regex]::Escape($Key) + "=") } | Select-Object -Last 1)
  if (-not $line) { return $Default }
  $parts = $line -split "=", 2
  if ($parts.Count -lt 2) { return $Default }
  $rawValue = ($parts[1] + "").Trim()
  $parsed = 0
  if ([int]::TryParse($rawValue, [ref]$parsed)) { return [int]$parsed }
  return $Default
}

function Get-ConfigTextValue {
  param(
    [string[]]$Lines,
    [string]$Key,
    [string]$Default = ""
  )
  if (-not $Lines -or $Lines.Count -eq 0) { return $Default }
  $line = ($Lines | Where-Object { $_ -match ("^" + [regex]::Escape($Key) + "=") } | Select-Object -Last 1)
  if (-not $line) { return $Default }
  $parts = $line -split "=", 2
  if ($parts.Count -lt 2) { return $Default }
  return (($parts[1] + "").Trim())
}

function Test-ConfigBoolValue {
  param(
    [string[]]$Lines,
    [string]$Key,
    [bool]$Default = $false
  )
  $fallback = if ($Default) { "1" } else { "0" }
  $raw = (Get-ConfigTextValue -Lines $Lines -Key $Key -Default $fallback).ToLowerInvariant()
  return ($raw -in @("1", "true", "yes", "on", "evet", "aktif"))
}

function Test-ServiceCopyCount {
  param(
    [string]$Name,
    [string]$Script,
    [int]$MaxCount = 2,
    [bool]$ShouldRun = $true
  )
  $scriptPattern = [regex]::Escape($Script)
  $procs = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^pythonw?\.exe$' -and
    $_.CommandLine -and
    $_.CommandLine -match 'D700_SERVICE_RUNNER\.py' -and
    $_.CommandLine -match $scriptPattern
  })
  if (-not $ShouldRun -and $procs.Count -gt 0 -and $StopRisky) {
    foreach ($p in $procs) {
      try {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        if (-not $Quiet) { Write-Host ("[FIX] kapali servis kopyasi durduruldu PID={0} {1}" -f $p.ProcessId, $Name) }
      } catch {}
    }
    Start-Sleep -Seconds 1
    $procs = @(Get-CimInstance Win32_Process | Where-Object {
      $_.Name -match '^pythonw?\.exe$' -and
      $_.CommandLine -and
      $_.CommandLine -match 'D700_SERVICE_RUNNER\.py' -and
      $_.CommandLine -match $scriptPattern
    })
  }
  if (-not $ShouldRun) {
    Write-Check "kapali servis kopyasi: $Name" ($procs.Count -eq 0) ("adet=" + $procs.Count)
    return
  }
  Write-Check "servis kopya kontrolu: $Name" ($procs.Count -le $MaxCount) ("adet=" + $procs.Count + " max=" + $MaxCount)
}

function Test-UrlOk {
  param(
    [string]$Url,
    [switch]$Insecure,
    [int]$TimeoutSec = 8
  )
  $args = @("-s", "--max-time", "$TimeoutSec", "-o", "NUL", "-w", "%{http_code}")
  if ($Insecure) { $args = @("-k") + $args }
  $args += $Url
  try {
    $code = (& curl.exe @args 2>$null).Trim()
    return $code -eq "200"
  } catch {
    return $false
  }
}

function Repair-PatientPortal {
  $portalScript = Join-Path $Root "D700_PATIENT_PORTAL_BASLAT.ps1"
  if (-not (Test-Path -LiteralPath $portalScript)) {
    if (-not $Quiet) { Write-Host "[WARN] Hasta portal repair script bulunamadi: $portalScript" }
    return
  }
  try {
    powershell -NoProfile -ExecutionPolicy Bypass -File $portalScript -Silent | Out-Null
    if (-not $Quiet) { Write-Host "[FIX] hasta portal yeniden baslatildi" }
    Start-Sleep -Seconds 2
  } catch {
    if (-not $Quiet) { Write-Host ("[WARN] hasta portal repair hata: {0}" -f $_.Exception.Message) }
  }
}

function Set-ConfigValue {
  param([string]$Key, [string]$Value)
  if (-not (Test-Path -LiteralPath $Config)) { return }
  $lines = @(Get-Content -LiteralPath $Config -Encoding UTF8)
  $found = $false
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match ("^" + [regex]::Escape($Key) + "=")) {
      $lines[$i] = "$Key=$Value"
      $found = $true
    }
  }
  if (-not $found) { $lines += "$Key=$Value" }
  Set-Content -LiteralPath $Config -Value $lines -Encoding UTF8
}

function Test-RiskAge {
  param($Proc, [datetime]$MinCreation)
  try {
    return ([datetime]$Proc.CreationDate) -lt $MinCreation
  } catch {
    return $true
  }
}

function Test-RiskProcess {
  param($Proc, [datetime]$MinCreation)
  if ($ExcludedPids -contains [int]$Proc.ProcessId) { return $false }
  if (-not $Proc.CommandLine) { return $false }
  if ($Proc.Name -notin @('powershell.exe','cmd.exe','python.exe','pythonw.exe')) { return $false }
  if (-not (Test-RiskAge $Proc $MinCreation)) { return $false }

  $cmd = [string]$Proc.CommandLine
  $cmdLower = $cmd.ToLowerInvariant()

  if ($cmdLower.Contains('get-ciminstance win32_process') -and
      -not $cmdLower.Contains('stop-process') -and
      -not $cmdLower.Contains('cmd /c')) {
    return $false
  }

  if ($Proc.Name -in @('python.exe','pythonw.exe')) {
    return (
      $cmdLower.Contains('codex_quick_check.py') -or
      $cmdLower.Contains(' -m py_compile ') -or
      $cmdLower.Contains('py_compile.compile') -or
      $cmdLower.Contains('ast.parse(src)') -or
      $cmdLower.Contains('d700_stabilite_tek_tik')
    )
  }

  return (
    $cmdLower.Contains('compile_web_out.txt') -or
    $cmdLower.Contains('compile_tmp.log') -or
    $cmdLower.Contains('quick_tmp.log') -or
    $cmdLower.Contains('web_ast_ok') -or
    $cmdLower.Contains('ast.parse(src)') -or
    $cmdLower.Contains('codex_quick_check.py') -or
    $cmdLower.Contains(' -m py_compile ') -or
    $cmdLower.Contains('d700_stabilite_tek_tik') -or
    $cmdLower.Contains('d700_admin_web_restart') -or
    $cmdLower.Contains('d700_baslat.bat')
  )
}

Push-Location $Root
try {
  Write-Host "D700 guvenli durum kontrolu: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
  $riskMinCreation = (Get-Date).AddSeconds(-[Math]::Max(0, [int]$RiskMinAgeSec))
  $cfgText = @()

  $risky = Get-CimInstance Win32_Process | Where-Object { Test-RiskProcess $_ $riskMinCreation }
  if ($risky -and $StopRisky) {
    foreach ($p in $risky) {
      try {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        if (-not $Quiet) { Write-Host ("[FIX] riskli kuyruk durduruldu PID={0} {1}" -f $p.ProcessId, $p.Name) }
      } catch {}
    }
    Start-Sleep -Seconds 1
    $risky = Get-CimInstance Win32_Process | Where-Object { Test-RiskProcess $_ $riskMinCreation }
  }
  Write-Check ("riskli tani/compile kuyrugu (>" + [int]$RiskMinAgeSec + "s)") (-not $risky) ("adet=" + @($risky).Count)
  if ($risky -and -not $Quiet) {
    $risky | Select-Object ProcessId,Name,CreationDate,CommandLine | Format-Table -AutoSize
  }

  if (Test-Path -LiteralPath $Config) {
    $cfgText = Get-Content -LiteralPath $Config -Encoding UTF8
    $owner = ($cfgText | Where-Object { $_ -match '^YAZKLINIK_HEALTH_WEB_ENFORCE_MANAGED_OWNER=' } | Select-Object -Last 1)
    $force = ($cfgText | Where-Object { $_ -match '^YAZKLINIK_HEALTH_WEB_ENFORCE_MANAGED_OWNER_FORCE=' } | Select-Object -Last 1)
    $managedStrict = $StrictManagedOwnerOff -or ((($env:YAZKLINIK_REQUIRE_MANAGED_OWNER_OFF + "") -eq "1"))
    $managedConfigNeedsRepair = (($owner -ne "YAZKLINIK_HEALTH_WEB_ENFORCE_MANAGED_OWNER=0") -or ($force -ne "YAZKLINIK_HEALTH_WEB_ENFORCE_MANAGED_OWNER_FORCE=0"))
    if ($managedStrict -and $PersistManagedOwnerOff -and $managedConfigNeedsRepair -and $RepairConfig) {
      Set-ConfigValue "YAZKLINIK_HEALTH_WEB_ENFORCE_MANAGED_OWNER" "0"
      Set-ConfigValue "YAZKLINIK_HEALTH_WEB_ENFORCE_MANAGED_OWNER_FORCE" "0"
      if (-not $Quiet) { Write-Host "[FIX] managed-owner config 0/0 yapildi" }
      $cfgText = Get-Content -LiteralPath $Config -Encoding UTF8
      $owner = ($cfgText | Where-Object { $_ -match '^YAZKLINIK_HEALTH_WEB_ENFORCE_MANAGED_OWNER=' } | Select-Object -Last 1)
      $force = ($cfgText | Where-Object { $_ -match '^YAZKLINIK_HEALTH_WEB_ENFORCE_MANAGED_OWNER_FORCE=' } | Select-Object -Last 1)
    } elseif ($managedStrict -and $RepairConfig -and $managedConfigNeedsRepair -and -not $PersistManagedOwnerOff -and -not $Quiet) {
      Write-Host "[WARN] strict-off aktif ama PersistManagedOwnerOff verilmedi; config zorla degistirilmedi"
    }
    if ($managedStrict) {
      Write-Check "managed-owner config (strict off)" (($owner -eq "YAZKLINIK_HEALTH_WEB_ENFORCE_MANAGED_OWNER=0") -and ($force -eq "YAZKLINIK_HEALTH_WEB_ENFORCE_MANAGED_OWNER_FORCE=0")) "$owner / $force"
    } else {
      Write-Check "managed-owner config" $true "$owner / $force"
    }
  } else {
    Write-Check "config.env" $false "bulunamadi"
  }

  Test-ServiceCopyCount "web" "yazklinik_web.py"
  Test-ServiceCopyCount "hasta portal" "yazklinik_patient_portal_public.py"
  Test-ServiceCopyCount "health monitor" "D700_HEALTH_MONITOR.py"
  Test-ServiceCopyCount "whisper" "yazklinik_whisper_service.py"
  Test-ServiceCopyCount "piper" "yazklinik_piper_service.py"
  Test-ServiceCopyCount "comfyui" "D700_COMFYUI_RUNNER.py"
  Test-ServiceCopyCount "sip alex" "yazklinik_sip_alex_client.py"
  $xttsEnabled = Test-ConfigBoolValue -Lines $cfgText -Key "YAZKLINIK_XTTS_ENABLED" -Default $false
  Test-ServiceCopyCount "xtts" "yazklinik_xtts_service.py" -ShouldRun:$xttsEnabled

  if (Test-Path -LiteralPath $HealthLog) {
    $tail = Get-Content -LiteralPath $HealthLog -Tail 80 -ErrorAction SilentlyContinue
    $lastOwner = ($tail | Where-Object { $_ -like '*managed-owner=*' } | Select-Object -Last 1)
    if ($StrictManagedOwnerOff -or ((($env:YAZKLINIK_REQUIRE_MANAGED_OWNER_OFF + "") -eq "1"))) {
      Write-Check "health monitor managed-owner (strict off)" ($lastOwner -like '*managed-owner=off*') "$lastOwner"
    } else {
      Write-Check "health monitor managed-owner" $true "$lastOwner"
    }
  } else {
    Write-Check "health monitor log" $false "bulunamadi"
  }

  $initialGraceSec = [Math]::Max(60, (Get-ConfigIntValue -Lines $cfgText -Key "YAZKLINIK_HEALTH_INITIAL_GRACE_SEC" -Default 180))
  $webRunnerPid = 0
  $webRunnerAgeSec = -1
  try {
    $webRunner = Get-CimInstance Win32_Process | Where-Object {
      $_.Name -match '^pythonw?\.exe$' -and
      $_.CommandLine -and
      $_.CommandLine -match 'D700_SERVICE_RUNNER\.py' -and
      $_.CommandLine -match 'yazklinik_web\.py'
    } | Sort-Object CreationDate -Descending | Select-Object -First 1
    if ($webRunner) {
      $webRunnerPid = [int]$webRunner.ProcessId
      $webRunnerAgeSec = [int][Math]::Max(0, ((Get-Date) - ([datetime]$webRunner.CreationDate)).TotalSeconds)
    }
  } catch {}
  $bootGraceActive = ($webRunnerPid -gt 0 -and $webRunnerAgeSec -ge 0 -and $webRunnerAgeSec -lt $initialGraceSec)
  if ($bootGraceActive) {
    Write-Check "web boot grace penceresi" $true ("pid=$webRunnerPid age=${webRunnerAgeSec}s < ${initialGraceSec}s")
  } elseif ($webRunnerPid -gt 0) {
    Write-Check "web boot grace penceresi" $true ("pid=$webRunnerPid age=${webRunnerAgeSec}s")
  } else {
    Write-Check "web runner process" $false "yok"
  }
  $bootGraceNote = if ($bootGraceActive) { "boot-grace: web yeni acilis penceresinde" } else { "" }

  Test-HttpBootAware "web 5052 giris" "http://127.0.0.1:5052/giris" -BootGraceActive:$bootGraceActive -BootGraceNote $bootGraceNote
  Test-HttpBootAware "https 5443 giris" "https://127.0.0.1:5443/giris" -Insecure -BootGraceActive:$bootGraceActive -BootGraceNote $bootGraceNote
  Test-HttpBootAware "web ping-fast" "http://127.0.0.1:5052/api/terminal/ping-fast" -BootGraceActive:$bootGraceActive -BootGraceNote $bootGraceNote
  if ($RequirePortal -or ((($env:YAZKLINIK_REQUIRE_PATIENT_PORTAL + "") -eq "1"))) {
    if ($RepairPortal -and -not (Test-UrlOk "http://127.0.0.1:5053/healthz")) {
      Repair-PatientPortal
    }
    Test-Http "hasta portal 5053" "http://127.0.0.1:5053/healthz"
  } else {
    Test-HttpOptional "hasta portal 5053 (opsiyonel)" "http://127.0.0.1:5053/healthz"
  }
  Test-HttpBootAware "public giris" "https://yazhakan.com.tr/giris" -Insecure -TimeoutSec 12 -BootGraceActive:$bootGraceActive -BootGraceNote $bootGraceNote

  if (Test-Path -LiteralPath $Python) {
    $dbCode = @"
import sqlite3, sys
p = r'D:\YazKlinik_Final_D700\local_db\yazklinik_v68.sqlite3'
con = sqlite3.connect(p, timeout=10)
qc = con.execute('PRAGMA quick_check').fetchone()[0]
fk = len(con.execute('PRAGMA foreign_key_check').fetchall())
con.close()
print('quick_check=' + str(qc) + '; foreign_key_rows=' + str(fk))
sys.exit(0 if qc == 'ok' and fk == 0 else 2)
"@
    $dbOut = & $Python -c $dbCode 2>&1
    Write-Check "sqlite butunluk" ($LASTEXITCODE -eq 0) (($dbOut | Out-String).Trim())
  } else {
    Write-Check "venv python" $false $Python
  }

  if ($FailCount -eq 0) {
    Write-Host "D700_GUVENLI_DURUM_OK"
    exit 0
  }
  Write-Host "D700_GUVENLI_DURUM_FAIL count=$FailCount"
  exit 1
} finally {
  Pop-Location
}
