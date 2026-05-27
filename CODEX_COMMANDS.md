# CODEX_COMMANDS.md - Yaygin gorevler + komutlar

> Codex CLI / Agent SDK icin kopyala-yapistir komutlar.

## Server Yonetimi

### Baslat (en kolay)
```powershell
D:\YazKlinik_Final_D700\D700_BASLAT.bat
```

### WebShell arayuzunu ac
```powershell
D:\YazKlinik_Final_D700\YazKlinik_WebShell_Windows.bat
```

### Manuel baslat (env var ile)
```powershell
Set-Location "D:\YazKlinik_Final_D700"
$env:YAZKLINIK_NAS_ROOT = "\\asustor\Voluson\Hastalar"
$env:YAZKLINIK_DB_PATH = "D:\YazKlinik_Final_D700\local_db\yazklinik_v68.sqlite3"
$env:YAZKLINIK_WEB_PORT="5052"
$env:YAZKLINIK_HTTPS_PORT="5443"
$env:YAZKLINIK_ENABLE_HTTPS="1"
$env:YAZKLINIK_WAITRESS_THREADS="12"
$env:PYTHONUNBUFFERED="1"
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP "yk_d700_runtime_pycache"
Start-Process -FilePath "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" `
  -ArgumentList "-u", "yazklinik_web.py" `
  -WorkingDirectory "D:\YazKlinik_Final_D700" -WindowStyle Hidden
```

### Durdur
```powershell
# Port 5052'deki PID'i bul ve oldur
$conn = Get-NetTCPConnection -LocalPort 5052 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force }

# Veya tum python procs (dikkat - baska Python varsa ona da etki eder)
Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force
```

### Restart
```powershell
# Once durdur, sonra baslat
Get-Process -Name python | Stop-Process -Force
Start-Sleep -Seconds 3
D:\YazKlinik_Final_D700\D700_BASLAT.bat
```

### Server canli mi check
```powershell
try {
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:5052/giris" -UseBasicParsing -TimeoutSec 3
  Write-Output "ALIVE - HTTP $($r.StatusCode)"
} catch {
  Write-Output "DOWN: $($_.Exception.Message)"
}
```

## Test ve Dogrulama

### D700 mobil scroll smoke (onerilen)
```powershell
Set-Location "D:\YazKlinik_Final_D700"
& "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" CODEX_MOBILE_SCROLL_CHECK.py
```

### D700 quick check + mobil smoke (strict)
```powershell
Set-Location "D:\YazKlinik_Final_D700"
& "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" CODEX_QUICK_CHECK.py --mobile-scroll-strict
```

### D700 tek tik strict dogrulama (.bat)
```powershell
D:\YazKlinik_Final_D700\D700_QUICK_CHECK_MOBILE_STRICT.bat
```
Not: Self-heal varsayilan olarak kapali. Gerekiyorsa once `set YAZKLINIK_QUICKCHECK_SELFHEAL=1` ver.

### D700 stabilite tek tik (onerilen operasyon komutu)
```powershell
D:\YazKlinik_Final_D700\D700_STABILITE_TEK_TIK.bat
```
Not: Web self-heal + strict quick-check (mobil dahil) zincirini otomatik calistirir.

### D700 stabilite soak (ardisik kanit)
```powershell
# 2 tur, turlar arasi 5 sn bekleme
D:\YazKlinik_Final_D700\D700_STABILITE_SOAK.bat 2 5
```
Not: Her turda tek-tik stabilite calisir; ilk hatada durur.

### D700 web self-heal (hizli)
```powershell
D:\YazKlinik_Final_D700\D700_WEB_SELF_HEAL_CHECK.bat
```

### D700 user-level web restart (admin yoksa fallback)
```powershell
D:\YazKlinik_Final_D700\D700_USER_WEB_RESTART.bat
```

### Sistem health check
```powershell
Set-Location "D:\YazKlinik_Final_D700"
& "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" CODEX_QUICK_CHECK.py
```

### Hasta portal ayrimi + genel sistem (tek tik)
```powershell
D:\YazKlinik_Final_D700\D700_PATIENT_PORTAL_TEK_TIK_KONTROL.bat
```
Not: Once `CODEX_QUICK_CHECK.py`, sonra `D700_PATIENT_PORTAL_SPLIT_CHECK.py` calisir.

### Sadece compile check
```powershell
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP "yk_d700_compile_pycache"
& "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" -m py_compile `
  "D:\YazKlinik_Final_D700\yazklinik_web.py" `
  "D:\YazKlinik_Final_D700\yazklinik_v68.py" `
  "D:\YazKlinik_Final_D700\yazklinik_feature_sync.py"
if ($?) { Write-Output "COMPILE_OK" } else { Write-Output "COMPILE_FAIL" }
```

### Login + smoke test
```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$login = Invoke-WebRequest -Uri "http://127.0.0.1:5052/giris" `
  -Method POST -Body @{username="doktor"; password="1133"} `
  -WebSession $session -UseBasicParsing -MaximumRedirection 5
Write-Output "Login: $($login.StatusCode)"

# Test bir route
$r = Invoke-WebRequest -Uri "http://127.0.0.1:5052/hastalar" -WebSession $session -UseBasicParsing
Write-Output "Status: $($r.StatusCode) Size: $($r.RawContentLength)"
```

### Toplu route smoke test
```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-WebRequest -Uri "http://127.0.0.1:5052/giris" -Method POST `
  -Body @{username="doktor"; password="1133"} -WebSession $session `
  -UseBasicParsing -MaximumRedirection 5 | Out-Null

$tests = @(
  "/hastalar", "/tedavi-planla", "/sistem-ayarlari",
  "/akilli-dialog", "/hasta-birlestir", "/obgyn-rehber",
  "/diyet-rehberi", "/ivf-konsult", "/api/sistem-durumu"
)
$ok=0; $err=0
foreach ($u in $tests) {
  try {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:5052$u" -WebSession $session `
      -UseBasicParsing -TimeoutSec 12
    $sw.Stop()
    Write-Output ("  [OK {0,4}ms] {1}" -f $sw.ElapsedMilliseconds, $u)
    $ok++
  } catch {
    Write-Output ("  [ERR] $u : $($_.Exception.Message)")
    $err++
  }
}
Write-Output "RESULT: OK=$ok ERR=$err"
```

## DB Komutlari

### DB'ye baglan + sorgu
```powershell
& "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" -c @"
import sqlite3
con = sqlite3.connect(r'D:\YazKlinik_Final_D700\local_db\yazklinik_v68.sqlite3')
con.row_factory = lambda cur, row: {d[0]: row[i] for i, d in enumerate(cur.description)}
print('patients:', con.execute('SELECT COUNT(*) FROM patients').fetchone())
print('visits:', con.execute('SELECT COUNT(*) FROM visits').fetchone())
print('files:', con.execute('SELECT COUNT(*) FROM files').fetchone())
con.close()
"@
```

### DB schema dump
```powershell
& "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" -c @"
import sqlite3
con = sqlite3.connect(r'D:\YazKlinik_Final_D700\local_db\yazklinik_v68.sqlite3')
for r in con.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\"):
    print(r[0])
"@
```

### DB integrity check
```powershell
& "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" -c "
import sqlite3
con = sqlite3.connect(r'D:\YazKlinik_Final_D700\local_db\yazklinik_v68.sqlite3')
print('integrity:', con.execute('PRAGMA integrity_check').fetchone())
print('journal_mode:', con.execute('PRAGMA journal_mode').fetchone())
con.close()
"
```

### Manuel DB yedek
```powershell
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item `
  "D:\YazKlinik_Final_D700\local_db\yazklinik_v68.sqlite3" `
  "D:\YazKlinik_Final_D700\auto_backups\manual_yedek_$ts.sqlite3"
```

## Log Komutlari

### Server stdout log
```powershell
Get-Content "D:\YazKlinik_Final_D700\D700_server.log" -Tail 50
# Devam eden takip:
Get-Content "D:\YazKlinik_Final_D700\D700_server.log" -Tail 20 -Wait
```

### Server stderr log
```powershell
Get-Content "D:\YazKlinik_Final_D700\D700_server_HATA.log" -Tail 30
```

### 500 hata yakalama (foreground)
```powershell
Get-Process -Name python | Stop-Process -Force
Start-Sleep -Seconds 3
Set-Location "D:\YazKlinik_Final_D700"
$env:YAZKLINIK_DB_PATH="D:\YazKlinik_Final_D700\local_db\yazklinik_v68.sqlite3"
$env:YAZKLINIK_WEB_PORT="5052"
$env:YAZKLINIK_ENABLE_HTTPS="0"
$env:PYTHONUNBUFFERED="1"
& "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" -u yazklinik_web.py
# (Ctrl+C ile durdur)
```

## NAS / Asustor

### NAS erisim test
```powershell
@("\\asustor", "\\asustor\Voluson", "\\asustor\Voluson\Hastalar") | ForEach-Object {
  Write-Output "$_  -> $(Test-Path $_)"
}
```

### NAS map drive (Z: olarak)
```powershell
# Calisan oturum icin
net use Z: \\asustor\Voluson /persistent:yes /user:DOMAIN\user PASSWORD
```

### NAS hasta klasorleri listele
```powershell
Get-ChildItem "\\asustor\Voluson\Hastalar" -Directory | Select-Object -First 20 Name, LastWriteTime
```

## Dosya Bulma / Ekleme

### Belirli string'i kodda ara (D700 klasorunde)
```powershell
Set-Location "D:\YazKlinik_Final_D700"
Get-ChildItem -Recurse -Filter "*.py" | Select-String -Pattern "PRODUCT_EDITION" | Select-Object -First 5
```

### Yeni route eklemek icin yer bul
```powershell
# yazklinik_web.py'da @app.route satirlarini listele
Get-Content "D:\YazKlinik_Final_D700\yazklinik_web.py" |
  Select-String -Pattern '^@app\.route' |
  ForEach-Object { "$($_.LineNumber): $($_.Line)" } |
  Select-Object -First 30
```

## Cache Temizleme

### Pycache temizle
```powershell
Remove-Item "$env:TEMP\yk_d700_*" -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem "D:\YazKlinik_Final_D700" -Recurse -Directory -Filter "__pycache__" |
  Remove-Item -Recurse -Force
```

### WAL ve SHM temizle (DB lock uyarisi sonrasi)
```powershell
Get-Process -Name python | Stop-Process -Force
Start-Sleep -Seconds 3
@("yazklinik_v68.sqlite3-wal", "yazklinik_v68.sqlite3-shm") | ForEach-Object {
  $f = "D:\YazKlinik_Final_D700\local_db\$_"
  if (Test-Path $f) { Remove-Item $f -Force; Write-Output "  Silindi: $_" }
}
```

## D104 -> D700 Sync (D104 hala kullaniliyorsa)

### Tek dosya sync
```powershell
@("yazklinik_web.py", "yazklinik_v68.py", "yazklinik_feature_sync.py") | ForEach-Object {
  Copy-Item "<ESKI_D104_KLASORU>\$_" `
    "D:\YazKlinik_Final_D700\$_" -Force
  $a = (Get-FileHash "<ESKI_D104_KLASORU>\$_" -Algorithm SHA1).Hash
  $b = (Get-FileHash "D:\YazKlinik_Final_D700\$_" -Algorithm SHA1).Hash
  Write-Output "  $_ : $(if ($a -eq $b) { 'SYNC OK' } else { 'DIFF!' })"
}
```

## Codex Workflow (one-liner'lar)

### "Ek bir route ekle" workflow
1. `Read AGENTS.md` Ã¢â€ â€™ bagli kurallari oku
2. `Grep "@app.route" yazklinik_web.py` Ã¢â€ â€™ benzer route'u bul
3. `Edit` ile route ekle (yakin route'un yanina)
4. Compile check (yukaridaki komut)
5. Restart + smoke test (yukaridaki komut)
6. Kullaniciya rapor: "Yaptim. /yeni-route eklendi, OK. compile OK, server 200."

### "Hata var, debug" workflow
1. `Get-Content D700_server_HATA.log -Tail 30`
2. `Get-Content D700_server.log -Tail 50`
3. Server foreground baslat (yukaridaki komut) -> hata gor
4. `Grep "<hata mesaji>" yazklinik_web.py` -> kaynak bul
5. Edit (kucuk patch) + compile + restart + verify

### "Performans iyilestir" workflow
1. `CODEX_QUICK_CHECK.py` -> mevcut durumu olc
2. Smoke test -> hangi route yavas
3. Cache TTL artir + DB query optimize
4. Restart + benchmark karsilastir

## Ortam Degiskenleri (env var) - Tam Liste

| Env | Default | Ne |
|---|---|---|
| `YAZKLINIK_NAS_ROOT` | `\\asustor\Voluson\Hastalar` | NAS hasta paylasimi |
| `YAZKLINIK_DB_PATH` | `D:\YazKlinik_Final_D700\local_db\yazklinik_v68.sqlite3` | Lokal DB |
| `YAZKLINIK_DB_ROOT` | (yok) | DB root (DB_PATH var ise gerekmez) |
| `YAZKLINIK_WEB_PORT` | `5052` | HTTP port |
| `YAZKLINIK_HTTPS_PORT` | `5443` | HTTPS port |
| `YAZKLINIK_ENABLE_HTTPS` | `1` | HTTPS aktif/pasif |
| `YAZKLINIK_WAITRESS_THREADS` | `12` | Server thread sayisi |
| `YAZKLINIK_BACKUP_ROOT` | `D:\YazKlinik_Final_D700\auto_backups` | Yedek klasoru |
| `YAZKLINIK_AUTO_BACKUP_INTERVAL_SEC` | `86400` (24sa) | Yedek araligi |
| `YAZKLINIK_AUTO_BACKUP_INITIAL_DELAY_SEC` | `900` (15dk) | Ilk yedek delay |
| `YAZKLINIK_VOLUSON_AUTO_PREFIX` | `F137230` | Voluson hasta klasor oneki |
| `YAZKLINIK_SERVER_ENGINE` | `waitress` | Flask sunucu engine |
| `PYTHONUTF8` | `1` | Python UTF-8 mod |
| `PYTHONIOENCODING` | `utf-8` | stdout encoding |
| `PYTHONUNBUFFERED` | `1` | Stdout buffer kapali |
| `PYTHONPYCACHEPREFIX` | `%TEMP%\yk_d700_runtime_pycache` | Pycache klasoru |







