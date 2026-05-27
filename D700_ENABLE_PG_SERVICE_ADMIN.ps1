param(
  [string]$ServiceName = "postgresql-d700",
  [string]$PgCtl = "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe",
  [string]$PgData = "C:\Program Files\PostgreSQL\17\data"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $PgCtl)) { throw "pg_ctl bulunamadi: $PgCtl" }
if (-not (Test-Path $PgData)) { throw "PGDATA bulunamadi: $PgData" }

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $svc) {
  & $PgCtl register -N $ServiceName -D $PgData -S auto
  if ($LASTEXITCODE -ne 0) {
    throw "Service register basarisiz. Bu scripti yonetici (Run as Administrator) olarak calistir."
  }
}

& $PgCtl stop -D $PgData -m fast | Out-Null
Start-Sleep -Seconds 2
Start-Service -Name $ServiceName
Set-Service -Name $ServiceName -StartupType Automatic

Get-Service -Name $ServiceName | Select-Object Name, Status, StartType | Format-Table -AutoSize
Write-Host "PG_SERVICE_OK"
