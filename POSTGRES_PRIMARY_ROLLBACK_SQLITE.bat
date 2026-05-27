@echo off
setlocal
cd /d "%~dp0"

if /I not "%~1"=="--confirm" (
  echo [KORUMA] Bu dosya PostgreSQL primary sistemini SQLite shadow moduna dondurur.
  echo [KORUMA] Yanlislikla calismamasi icin islem durduruldu.
  echo.
  echo Gercekten rollback gerekiyorsa:
  echo   POSTGRES_PRIMARY_ROLLBACK_SQLITE.bat --confirm
  exit /b 1
)

echo PostgreSQL primary rollback -> SQLite shadow...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='config.env'; $stamp=Get-Date -Format 'yyyyMMdd_HHmmss'; Copy-Item -LiteralPath $p -Destination ('auto_backups\\config_env_before_sqlite_rollback_' + $stamp + '.env') -Force; $t=Get-Content $p -Raw -Encoding UTF8; $pairs=@{'YAZKLINIK_DB_DIALECT'='sqlite'; 'YAZKLINIK_DB_PRIMARY'='sqlite'; 'YAZKLINIK_POSTGRES_MODE'='shadow'; 'YAZKLINIK_POSTGRES_RUNTIME_ADAPTER_READY'='0'; 'YAZKLINIK_POSTGRES_SQL_COMPAT_READY'='0'}; foreach($k in $pairs.Keys){ if($t -match ('(?m)^' + [regex]::Escape($k) + '=')){ $t=[regex]::Replace($t, ('(?m)^' + [regex]::Escape($k) + '=.*$'), ($k + '=' + $pairs[$k])) } else { $t += \"`n$k=$($pairs[$k])\" } }; Set-Content -Path $p -Value $t -Encoding UTF8"
echo Done. Restarting D500_BASLAT.bat
call D500_BASLAT.bat
