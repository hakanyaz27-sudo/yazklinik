param(
  [string]$PgBin = "C:\Program Files\PostgreSQL\17\bin",
  [string]$PgHost = "127.0.0.1",
  [int]$PgPort = 5432,
  [string]$PgUser = "postgres",
  [string]$PostgresPassword = "",
  [string]$BaseRoot = "D:\pg\basebackup",
  [string]$WalArchive = "D:\pg\wal_archive",
  [string]$LogRoot = "D:\pg\logs",
  [int]$RetentionDays = 14
)

$ErrorActionPreference = "Stop"

function Get-PostgresPassword {
  param([string]$ExplicitPassword)
  if (-not [string]::IsNullOrWhiteSpace($ExplicitPassword)) {
    return $ExplicitPassword
  }
  if ($env:D700_PG_PASSWORD) {
    return $env:D700_PG_PASSWORD
  }

  $dsnLine = docker inspect pg_exporter --format "{{range .Config.Env}}{{println .}}{{end}}" 2>$null |
    Select-String "^DATA_SOURCE_NAME="
  if ($dsnLine) {
    $dsn = ($dsnLine.ToString() -replace "^DATA_SOURCE_NAME=", "").Trim()
    try {
      $uri = [Uri]$dsn
      if ($uri.UserInfo -and $uri.UserInfo.Contains(":")) {
        return [Uri]::UnescapeDataString(($uri.UserInfo.Split(":", 2)[1]))
      }
    } catch {
      # DSN parse edilemezse asagida net hata verilecek.
    }
  }

  throw "PostgreSQL sifresi bulunamadi. Parametre -PostgresPassword verin veya D700_PG_PASSWORD env ayarlayin."
}

New-Item -ItemType Directory -Force -Path $BaseRoot, $WalArchive, $LogRoot | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runLog = Join-Path $LogRoot ("pg_daily_backup_" + $stamp + ".log")
Start-Transcript -Path $runLog -Append | Out-Null

$pgPass = $null
$backupDir = $null

try {
  $pgPass = Get-PostgresPassword -ExplicitPassword $PostgresPassword
  $env:PGPASSWORD = $pgPass

  & (Join-Path $PgBin "pg_isready.exe") -h $PgHost -p $PgPort | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL hazir degil (pg_isready fail)."
  }

  $backupDir = Join-Path $BaseRoot ("base_" + $stamp)
  & (Join-Path $PgBin "pg_basebackup.exe") `
    -h $PgHost `
    -p $PgPort `
    -U $PgUser `
    -D $backupDir `
    -Fp `
    -X stream `
    -P `
    -R
  if ($LASTEXITCODE -ne 0) {
    throw "pg_basebackup basarisiz. ExitCode=$LASTEXITCODE"
  }

  & (Join-Path $PgBin "psql.exe") -h $PgHost -p $PgPort -U $PgUser -d postgres -Atc "SELECT pg_switch_wal();" | Out-Null
  Start-Sleep -Seconds 2

  $walCount = (Get-ChildItem -Path $WalArchive -File -ErrorAction SilentlyContinue | Measure-Object).Count
  if ($walCount -lt 1) {
    throw "WAL arsivinde dosya yok: $WalArchive"
  }

  Get-ChildItem -Path $BaseRoot -Directory -Filter "base_*" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1 * $RetentionDays) } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

  Write-Host "D700_DAILY_BACKUP_OK"
  Write-Host ("BACKUP_PATH=" + $backupDir)
  Write-Host ("WAL_FILE_COUNT=" + $walCount)
}
finally {
  Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
  Stop-Transcript | Out-Null
}
