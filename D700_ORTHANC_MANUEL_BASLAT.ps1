param(
    [ValidateSet("start", "stop", "status")]
    [string]$Mode = "start",
    [int]$Quiet = 0
)

$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$serviceName = if ($env:YAZKLINIK_ORTHANC_SERVICE_NAME) { $env:YAZKLINIK_ORTHANC_SERVICE_NAME } else { "Orthanc" }
$orthancDir = if ($env:YAZKLINIK_ORTHANC_DIR) { $env:YAZKLINIK_ORTHANC_DIR } else { "E:\Orthanc Server" }
$orthancExe = if ($env:YAZKLINIK_ORTHANC_EXE) { $env:YAZKLINIK_ORTHANC_EXE } else { Join-Path $orthancDir "Orthanc.exe" }
$orthancCfg = if ($env:YAZKLINIK_ORTHANC_CONFIG) { $env:YAZKLINIK_ORTHANC_CONFIG } else { Join-Path $orthancDir "Configuration\config.json" }
$logPath = Join-Path $root "D700_orthanc_manual.log"

function Write-Quiet {
    param([string]$Text)
    if ($Quiet -eq 0) { Write-Host $Text }
}

function Test-OrthancPortReady {
    $listening = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 8042, 4242 } |
        Select-Object -ExpandProperty LocalPort -Unique
    return ($listening -contains 8042) -and ($listening -contains 4242)
}

function Get-OrthancStatus {
    $svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($svc) { return [string]$svc.Status }
    return "NOT_FOUND"
}

function Get-OrthancProcess {
    if (-not (Test-Path -LiteralPath $orthancExe)) { return $null }
    $target = [IO.Path]::GetFullPath($orthancExe)
    return (Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -ieq "Orthanc.exe" -and
            $_.ExecutablePath -and
            ([IO.Path]::GetFullPath($_.ExecutablePath) -eq $target)
        } |
        Select-Object -First 1)
}

function Get-OrthancPorts {
    $ports = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 8042, 4242 } |
        Sort-Object LocalPort |
        ForEach-Object { "{0}:{1}" -f $_.LocalAddress, $_.LocalPort }
    if ($ports) { return ($ports -join "; ") }
    return "NONE"
}

function Log-Event {
    param([string]$Message)
    $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    Add-Content -LiteralPath $logPath -Value ("{0} {1}" -f $stamp, $Message)
}

switch ($Mode) {
    "stop" {
        Write-Quiet "[+] Orthanc durduruluyor..."
        $svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -eq "Running") {
            Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
        }
        if (Test-Path -LiteralPath $orthancDir) {
            $rootFull = [IO.Path]::GetFullPath($orthancDir)
            Get-CimInstance Win32_Process |
                Where-Object {
                    $_.Name -ieq "Orthanc.exe" -and
                    $_.ExecutablePath -and
                    ([IO.Path]::GetFullPath($_.ExecutablePath)).StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)
                } |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        }
        Log-Event "mode=stop"
        Write-Quiet "[OK] Orthanc stop komutu gonderildi."
        exit 0
    }
    "status" {
        $svcState = Get-OrthancStatus
        $proc = Get-OrthancProcess
        $procText = if ($proc) { "RUNNING (PID=$($proc.ProcessId))" } else { "STOPPED" }
        $ports = Get-OrthancPorts
        $ready = Test-OrthancPortReady
        Write-Quiet ("Service durumu: {0}" -f $svcState)
        Write-Quiet ("Process      : {0}" -f $procText)
        Write-Quiet ("Portlar      : {0}" -f $ports)
        Write-Quiet ("Hazir        : {0}" -f $(if ($ready) { "EVET" } else { "HAYIR" }))
        Log-Event ("mode=status service={0} process={1} ready={2} ports={3}" -f $svcState, $procText, $(if ($ready) { "1" } else { "0" }), $ports)
        exit 0
    }
    default {
        Write-Quiet "[+] Orthanc baslatiliyor..."

        $svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -ne "Running") {
            Start-Service -Name $serviceName -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }

        if ((Test-Path -LiteralPath $orthancExe) -and (Test-Path -LiteralPath $orthancCfg)) {
            $running = Get-OrthancProcess
            if (-not $running) {
                # Start-Process ArgumentList joins tokens into one string; keep cfg path quoted
                # so "E:\Orthanc Server\Configuration\config.json" is passed as one argument.
                $cfgArg = '"' + $orthancCfg + '"'
                Start-Process -FilePath $orthancExe -ArgumentList $cfgArg -WorkingDirectory $orthancDir -WindowStyle Hidden
            }
        }

        $ready = $false
        for ($i = 0; $i -lt 60; $i++) {
            if (Test-OrthancPortReady) {
                $ready = $true
                break
            }
            Start-Sleep -Seconds 1
        }

        if ($ready) {
            Write-Quiet "[OK] Orthanc portlari hazir (8042/4242)."
        } else {
            Write-Quiet "[!] Orthanc portlari henuz hazir degil."
        }
        $proc = Get-OrthancProcess
        $procText = if ($proc) { "RUNNING (PID=$($proc.ProcessId))" } else { "STOPPED" }
        Log-Event ("mode=start ready={0} process={1}" -f ($(if ($ready) { "1" } else { "0" })), $procText)
        exit 0
    }
}

