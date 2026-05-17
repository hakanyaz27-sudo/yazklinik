# YazKlinik D300 - Restic Gunluk Otomatik Yedek
# Task Scheduler ile her gun 03:00'te calistir:
#   schtasks /create /tn "YazKlinik Restic Daily" /tr "powershell.exe -ExecutionPolicy Bypass -File D:\YazKlinik_Final_D300\akillilik\scripts\restic_daily_backup.ps1" /sc daily /st 03:00 /rl HIGHEST
#
# Manuel calistirmak icin: .\restic_daily_backup.ps1
#
# Yedeklenenler:
#   - local_db (hasta SQLite)
#   - rag_data (Alex vector DB)
#   - akillilik/data (Vaultwarden, n8n, Open WebUI, OHIF, Stirling)
#   - static (CSS, logolar)
#   - config.env
# Retention: gunluk 7, haftalik 4, aylik 12

$ErrorActionPreference = "Stop"
$root = "D:\YazKlinik_Final_D300"
$repo = "$root\backup\restic-repo"
$passFile = "$root\backup\.restic-pass"
$log = "$root\backup\restic-daily.log"
$resticBin = (Get-Command restic -EA SilentlyContinue).Source
if (-not $resticBin) {
    $resticBin = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "restic*.exe" -EA SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $resticBin -or -not (Test-Path $passFile) -or -not (Test-Path "$repo\config")) {
    "[$(Get-Date)] HATA: restic ya da repo eksik" | Out-File $log -Append
    exit 1
}

$env:RESTIC_PASSWORD_FILE = $passFile
$env:RESTIC_REPOSITORY = $repo
$tag = "daily-" + (Get-Date -Format yyyy-MM-dd)

"[$(Get-Date)] === Yedek basliyor ===" | Out-File $log -Append
& $resticBin backup `
    "$root\local_db" `
    "$root\rag_data" `
    "$root\akillilik\data" `
    "$root\static" `
    "$root\config.env" `
    --tag $tag --tag d300-daily 2>&1 | Out-File $log -Append
$bk = $LASTEXITCODE

"[$(Get-Date)] === Retention forget ===" | Out-File $log -Append
& $resticBin forget --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --prune 2>&1 | Out-File $log -Append

"[$(Get-Date)] === BITTI (backup exit $bk) ===" | Out-File $log -Append
exit $bk
