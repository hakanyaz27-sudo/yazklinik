param(
  [string]$PgBin = "C:\Program Files\PostgreSQL\17\bin",
  [string]$BaseRoot = "D:\pg\basebackup",
  [string]$ProbeRoot = "D:\pg\restore_probe",
  [string]$LogRoot = "D:\pg\logs",
  [int]$ProbeRetentionDays = 30
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $BaseRoot, $ProbeRoot, $LogRoot | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runLog = Join-Path $LogRoot ("pg_monthly_restore_smoke_" + $stamp + ".log")
Start-Transcript -Path $runLog -Append | Out-Null

try {
  $latest = Get-ChildItem -Path $BaseRoot -Directory -Filter "base_*" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if (-not $latest) {
    throw "Base backup bulunamadi: $BaseRoot"
  }

  & (Join-Path $PgBin "pg_verifybackup.exe") $latest.FullName | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "pg_verifybackup basarisiz. ExitCode=$LASTEXITCODE"
  }

  $probePath = Join-Path $ProbeRoot ("probe_" + $stamp)
  New-Item -ItemType Directory -Force -Path $probePath | Out-Null

  $null = robocopy $latest.FullName $probePath /E /NFL /NDL /NJH /NJS /NP
  if ($LASTEXITCODE -ge 8) {
    throw "Probe kopyalama basarisiz. RobocopyExit=$LASTEXITCODE"
  }

  if (-not (Test-Path (Join-Path $probePath "PG_VERSION"))) {
    throw "Restore probe dogrulanamadi: PG_VERSION yok ($probePath)"
  }

  Get-ChildItem -Path $ProbeRoot -Directory -Filter "probe_*" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1 * $ProbeRetentionDays) } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

  Write-Host "D700_MONTHLY_RESTORE_SMOKE_OK"
  Write-Host ("LATEST_BACKUP=" + $latest.FullName)
  Write-Host ("RESTORE_PROBE_PATH=" + $probePath)
}
finally {
  Stop-Transcript | Out-Null
}
