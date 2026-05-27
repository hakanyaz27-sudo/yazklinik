# YazKlinik D700 - NAS Yedek Saglik Kontrolu (6 saatte bir)
# yazklinik_nas_yedek_izleyici_agent kullanir.

$root = "D:\YazKlinik_Final_D500"
$venv = "$root\.venv\Scripts\python.exe"
$log = "$root\backup\nas-health.log"
$nasRoot = $env:YAZKLINIK_NAS_ROOT
if (-not $nasRoot) { $nasRoot = "\\asustor\Voluson" }

$pyScript = @"
import sys, json
sys.path.insert(0, r'$root')
from yazklinik_nas_yedek_izleyici_agent import check_health
r = check_health(r'$nasRoot')
print(json.dumps({
    'reachable': r.nas_reachable,
    'backups': r.backup_count,
    'disk_used_pct': r.disk_used_pct,
    'warnings': r.warnings,
    'critical': r.critical,
}, ensure_ascii=False, indent=2))
"@

$pyScript | Out-File -Encoding utf8 "$env:TEMP\yk_nas_check.py"
"[$(Get-Date)] === NAS health check ===" | Out-File $log -Append
& $venv "$env:TEMP\yk_nas_check.py" 2>&1 | Out-File $log -Append

# Kritik durumda Windows toast bildirim (opsiyonel)
$lastResult = Get-Content $log -Tail 30 -Raw
if ($lastResult -match '"critical": \[\s*"') {
    Write-EventLog -LogName Application -Source "YazKlinik" -EntryType Error -EventId 9999 `
        -Message "NAS kritik durum: detay $log" -EA SilentlyContinue
}

