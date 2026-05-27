param(
  [Parameter(Mandatory = $true)]
  [string]$PostgresPassword,
  [string]$PostgresUser = "postgres"
)

$ErrorActionPreference = "Stop"

$PGROOT = "C:\Program Files\PostgreSQL\17"
$PGBIN = Join-Path $PGROOT "bin"
$PGDATA = Join-Path $PGROOT "data"
$ARCH = "D:\pg\wal_archive"
$BASE = "D:\pg\basebackup"
$OBS = "D:\obs"
$CfgPath = Join-Path $PGDATA "postgresql.conf"

function Set-PgConfValue {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Key,
    [Parameter(Mandatory = $true)][string]$Value
  )
  $pattern = "^\s*#?\s*" + [regex]::Escape($Key) + "\s*=.*$"
  $line = "$Key = $Value"
  $content = Get-Content -Path $Path
  if ($content -match $pattern) {
    $content = $content -replace $pattern, $line
  } else {
    $content += $line
  }
  Set-Content -Path $Path -Value $content -Encoding ascii
}

Write-Host "[1/7] Dizinler hazirlaniyor..."
New-Item -ItemType Directory -Force -Path $ARCH, $BASE, $OBS | Out-Null

Write-Host "[2/7] PostgreSQL cluster kontrol..."
if (-not (Test-Path (Join-Path $PGDATA "PG_VERSION"))) {
  if (-not (Test-Path $PGDATA)) {
    New-Item -ItemType Directory -Force -Path $PGDATA | Out-Null
  }
  $existing = Get-ChildItem -Path $PGDATA -Force -ErrorAction SilentlyContinue
  if ($existing.Count -gt 0) {
    throw "PGDATA dolu gorunuyor: $PGDATA. Devam etmeden once dizini bosalt veya farkli bir PGDATA sec."
  }

  $pwFile = Join-Path $env:TEMP ("pg_pw_" + [guid]::NewGuid().ToString("N") + ".txt")
  Set-Content -Path $pwFile -Value $PostgresPassword -Encoding ascii
  try {
    & (Join-Path $PGBIN "initdb.exe") `
      -D $PGDATA `
      --username=$PostgresUser `
      --pwfile=$pwFile `
      --auth=scram-sha-256 `
      --encoding=UTF8 `
      --locale=C
  } finally {
    Remove-Item -Path $pwFile -Force -ErrorAction SilentlyContinue
  }
}

if (-not (Test-Path $CfgPath)) {
  throw "postgresql.conf bulunamadi: $CfgPath"
}

Write-Host "[3/7] postgresql.conf guncelleniyor..."
Set-PgConfValue -Path $CfgPath -Key "wal_level" -Value "replica"
Set-PgConfValue -Path $CfgPath -Key "archive_mode" -Value "on"
Set-PgConfValue -Path $CfgPath -Key "archive_command" -Value "'copy `"%p`" `"D:/pg/wal_archive/%f`"'"
Set-PgConfValue -Path $CfgPath -Key "shared_preload_libraries" -Value "'pg_stat_statements'"
Set-PgConfValue -Path $CfgPath -Key "compute_query_id" -Value "on"

Write-Host "[4/7] PostgreSQL baslat/restart..."
$logFile = Join-Path $PGDATA "server.log"
& (Join-Path $PGBIN "pg_ctl.exe") -D $PGDATA restart -l $logFile | Out-Null
if ($LASTEXITCODE -ne 0) {
  & (Join-Path $PGBIN "pg_ctl.exe") -D $PGDATA start -l $logFile | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL baslatilamadi. Log: $logFile"
  }
}
& (Join-Path $PGBIN "pg_isready.exe") -h 127.0.0.1 -p 5432 | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "PostgreSQL hazir degil (pg_isready fail)."
}

Write-Host "[5/7] pg_stat_statements extension..."
$env:PGPASSWORD = $PostgresPassword
& (Join-Path $PGBIN "psql.exe") -h 127.0.0.1 -U $PostgresUser -d postgres -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"
& (Join-Path $PGBIN "psql.exe") -h 127.0.0.1 -U $PostgresUser -d postgres -v ON_ERROR_STOP=1 -c "SELECT query,calls,total_exec_time FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 10;"

Write-Host "[6/7] Base backup..."
$backupPath = Join-Path $BASE ("full_" + (Get-Date -Format "yyyyMMdd_HHmm"))
& (Join-Path $PGBIN "pg_basebackup.exe") -h 127.0.0.1 -U $PostgresUser -D $backupPath -Ft -z -P

Write-Host "[7/7] Prometheus + Grafana + exporter..."
$promYaml = @'
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: "postgres_exporter"
    static_configs:
      - targets: ["host.docker.internal:9187"]
'@
Set-Content -Path "D:\obs\prometheus.yml" -Value $promYaml -Encoding ascii

docker rm -f pg_exporter prometheus grafana 2>$null | Out-Null
$null = $LASTEXITCODE
$exporterDsn = "postgresql://${PostgresUser}:${PostgresPassword}@host.docker.internal:5432/postgres?sslmode=disable"
docker run -d --name pg_exporter -p 9187:9187 -e "DATA_SOURCE_NAME=$exporterDsn" quay.io/prometheuscommunity/postgres-exporter:latest | Out-Null
docker run -d --name prometheus -p 9090:9090 -v "D:\obs\prometheus.yml:/etc/prometheus/prometheus.yml" prom/prometheus | Out-Null
$grafanaPort = 3000
if (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 3000 }) {
  $grafanaPort = 3002
}
docker run -d --name grafana -p "${grafanaPort}:3000" grafana/grafana-oss | Out-Null

Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "OK: PostgreSQL + WAL/PITR + pg_stat_statements + monitoring stack hazir."
Write-Host "Grafana: http://127.0.0.1:$grafanaPort"
