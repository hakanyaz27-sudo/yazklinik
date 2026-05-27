param(
    [string]$OutputDir = "",
    [int[]]$ServerIds = @(71238, 50529, 73426),
    [int]$RunsPerServer = 1
)

$ErrorActionPreference = "Stop"

function Resolve-SpeedtestPath {
    $candidates = @(
        "C:\Users\yazha\AppData\Local\Microsoft\WinGet\Packages\Ookla.Speedtest.CLI_Microsoft.Winget.Source_8wekyb3d8bbwe\speedtest.exe",
        "$env:ProgramFiles\Ookla\Speedtest CLI\speedtest.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    throw "speedtest.exe bulunamadi. Once Ookla Speedtest CLI kurun."
}

function New-OutputDir([string]$baseDir) {
    if ([string]::IsNullOrWhiteSpace($baseDir)) {
        $baseDir = Join-Path $PSScriptRoot "logs\upload_tests"
    }

    if (-not (Test-Path -LiteralPath $baseDir)) {
        New-Item -ItemType Directory -Path $baseDir -Force | Out-Null
    }

    return $baseDir
}

function Get-KillerAndAcronisStatus {
    $serviceNames = @(
        "Killer Network Service",
        "KNDBWM",
        "KAPSService",
        "Killer Analytics Service",
        "KillerSmartphoneSleepService",
        "AcronisActiveProtectionService",
        "AcronisCyberProtectionService"
    )

    return Get-Service -Name $serviceNames -ErrorAction SilentlyContinue |
        Select-Object Name, Status, StartType |
        Sort-Object Name
}

function Get-NicProfile {
    $props = @("Gigabit Lite", "Green Ethernet", "Power Saving Mode", "Priority & VLAN")
    return Get-NetAdapterAdvancedProperty -Name "Ethernet 2" -ErrorAction SilentlyContinue |
        Where-Object { $props -contains $_.DisplayName } |
        Select-Object DisplayName, DisplayValue |
        Sort-Object DisplayName
}

function Run-Speedtest([string]$exePath, [int]$serverId) {
    $raw = & $exePath --accept-license --accept-gdpr --server-id $serverId -f json
    if (-not $raw) {
        throw "Speedtest bos dondu (server id: $serverId)."
    }

    $firstJsonLine = $raw | Select-Object -First 1
    $obj = $firstJsonLine | ConvertFrom-Json

    return [pscustomobject]@{
        Timestamp  = $obj.timestamp
        ServerId   = $serverId
        Server     = ($obj.server.name + " - " + $obj.server.location)
        DownMbps   = [math]::Round(($obj.download.bandwidth * 8 / 1000000), 2)
        UpMbps     = [math]::Round(($obj.upload.bandwidth * 8 / 1000000), 2)
        PingMs     = [math]::Round($obj.ping.latency, 2)
        PacketLoss = [math]::Round([double]$obj.packetLoss, 2)
        ResultUrl  = $obj.result.url
    }
}

$speedtestExe = Resolve-SpeedtestPath
$outputFolder = New-OutputDir -baseDir $OutputDir
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outFile = Join-Path $outputFolder ("upload_kanit_" + $stamp + ".json")

$results = @()
foreach ($serverId in $ServerIds) {
    for ($i = 1; $i -le $RunsPerServer; $i++) {
        try {
            $results += Run-Speedtest -exePath $speedtestExe -serverId $serverId
        } catch {
            $results += [pscustomobject]@{
                Timestamp  = (Get-Date).ToString("s")
                ServerId   = $serverId
                Server     = "FAILED"
                DownMbps   = 0
                UpMbps     = 0
                PingMs     = 0
                PacketLoss = 0
                ResultUrl  = ""
                Error      = $_.Exception.Message
            }
        }
        Start-Sleep -Seconds 2
    }
}

$payload = [pscustomobject]@{
    GeneratedAt   = (Get-Date).ToString("s")
    ComputerName  = $env:COMPUTERNAME
    InterfaceInfo = Get-NetAdapter -Name "Ethernet 2" -ErrorAction SilentlyContinue |
        Select-Object Name, Status, LinkSpeed, InterfaceDescription
    NicProfile    = Get-NicProfile
    Services      = Get-KillerAndAcronisStatus
    Results       = $results
    AvgUploadMbps = [math]::Round((($results | Where-Object { $_.UpMbps -gt 0 } | Measure-Object UpMbps -Average).Average), 2)
    MaxUploadMbps = [math]::Round((($results | Where-Object { $_.UpMbps -gt 0 } | Measure-Object UpMbps -Maximum).Maximum), 2)
}

$payload | ConvertTo-Json -Depth 8 | Out-File -LiteralPath $outFile -Encoding utf8

"KAYIT: $outFile"
$results | Format-Table Timestamp, ServerId, Server, DownMbps, UpMbps, PingMs, PacketLoss -AutoSize
"AVG_UPLOAD_Mbps: $($payload.AvgUploadMbps)"
"MAX_UPLOAD_Mbps: $($payload.MaxUploadMbps)"
