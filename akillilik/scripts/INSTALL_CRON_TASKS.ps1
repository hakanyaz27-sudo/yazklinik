# YazKlinik D300 - Tum cron job'lari Windows Task Scheduler'a kur.
# Yonetici olarak calistir: Sag tik -> "Run with PowerShell" (Admin)

$root = "D:\YazKlinik_Final_D300\akillilik\scripts"
$tasks = @(
    @{name="YazKlinik_Restic_Daily"; script="$root\restic_daily_backup.ps1"; sc="DAILY"; time="03:00"; mo=""}
    @{name="YazKlinik_WA_Reminders"; script="$root\whatsapp_send_reminders.ps1"; sc="DAILY"; time="09:00"; mo=""}
    @{name="YazKlinik_NAS_Health"; script="$root\nas_health_check.ps1"; sc="HOURLY"; time=""; mo="6"}
)

foreach ($t in $tasks) {
    Write-Host "Kuruyor: $($t.name)"
    $a = @(
        "/create", "/tn", $t.name,
        "/tr", "powershell.exe -ExecutionPolicy Bypass -File `"$($t.script)`"",
        "/sc", $t.sc, "/rl", "HIGHEST", "/f"
    )
    if ($t.time) { $a += @("/st", $t.time) }
    if ($t.mo)   { $a += @("/mo", $t.mo) }
    & schtasks @a
    if ($LASTEXITCODE -eq 0) { Write-Host "  OK" -ForegroundColor Green }
    else { Write-Host "  HATA (admin olarak calistir)" -ForegroundColor Red }
}

Write-Host ""
Write-Host "Kontrol: schtasks /query /tn YazKlinik_Restic_Daily"
Write-Host "Sil: schtasks /delete /tn <name> /f"
