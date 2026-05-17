# YazKlinik D300 - Geri Cagirma Ajani WhatsApp Send Cron
# yazklinik_geri_cagirma_agent uretiyor "queued" mesajlari;
# bu script onlari yazklinik_whatsapp_local_helper ile gonderir.
# Task Scheduler her gun 09:00:
#   schtasks /create /tn "YazKlinik WA Reminders" /tr "powershell.exe -ExecutionPolicy Bypass -File D:\YazKlinik_Final_D300\akillilik\scripts\whatsapp_send_reminders.ps1" /sc daily /st 09:00 /rl HIGHEST

$root = "D:\YazKlinik_Final_D300"
$venv = "$root\.venv\Scripts\python.exe"
$log = "$root\backup\whatsapp-reminders.log"

"[$(Get-Date)] === geri cagirma WA cron basladi ===" | Out-File $log -Append

# Python helper script
$pyScript = @"
import sys, sqlite3, datetime
sys.path.insert(0, r'$root')
from yazklinik_geri_cagirma_agent import bulk_schedule, PatientCandidate

db = r'$root\local_db\yazklinik_v68.sqlite3'
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row

# Bugun + 7 gun arasi kontrol randevusu olan + KVKK rizali hastalari topla
# (Veritabani semasina gore degisir - asagisi ornek; gercek seman degisik ise uyarla)
candidates = []
today = datetime.date.today()
try:
    rows = con.execute(
        '''SELECT p.folder_key as patient_id, p.display_name as name, p.phone, v.visit_date as next_due
           FROM patients p LEFT JOIN visits v ON v.patient_folder_key = p.folder_key
           WHERE p.archived_at IS NULL AND v.visit_date BETWEEN date('now') AND date('now','+7 day')
           LIMIT 50''').fetchall()
    for r in rows:
        candidates.append(PatientCandidate(
            patient_id=r['patient_id'], name=r['name'] or '', phone=r['phone'] or '',
            next_due=r['next_due'], reason='gebelik_kontrol',
            consent_messaging=True))  # kvkk_consent kolonu varsa oradan oku
except Exception as e:
    print(f'DB query hata: {e}')

result = bulk_schedule(candidates, channel='whatsapp')
print(f'Queued: {len(result["queued"])}  Skipped: {len(result["skipped"])}')

# Gercek WhatsApp gonderim helper
try:
    from yazklinik_whatsapp_local_helper import send_whatsapp_message
    for job in result['queued']:
        try:
            r = send_whatsapp_message(job.phone, job.rendered_text)
            print(f'GONDERILDI: {job.phone} -> {r}')
        except Exception as e:
            print(f'HATA {job.phone}: {e}')
except ImportError:
    print('UYARI: yazklinik_whatsapp_local_helper.send_whatsapp_message bulunmadi')
"@

$pyScript | Out-File -Encoding utf8 "$env:TEMP\yk_wa_remind.py"
& $venv "$env:TEMP\yk_wa_remind.py" 2>&1 | Out-File $log -Append

"[$(Get-Date)] === BITTI ===" | Out-File $log -Append
