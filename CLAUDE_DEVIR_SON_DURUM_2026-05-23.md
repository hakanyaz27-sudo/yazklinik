# YAZKLINIK D700 - CLAUDE DEVIR DOSYASI (SON DURUM)

Tarih: 23.05.2026  
Proje yolu: `D:\YazKlinik_Final_D500`  
Hedef chat: Claude (devam calismasi icin)

---

## 1) Proje Ozeti

- Uygulama: YazKlinik Final D700 (OB-GYN klinik yonetim sistemi)
- Backend: Flask + Waitress + SQLite (lokal DB)
- Ana dosya: `yazklinik_web.py` (buyuk monolit)
- Baslatma: `D500_BASLAT.bat`
- Health monitor: `D500_HEALTH_MONITOR.py`
- Servis runner: `D500_SERVICE_RUNNER.py`
- Kritik endpointler:
  - `http://127.0.0.1:5052`
  - `https://127.0.0.1:5443`

---

## 2) Bu Seansa Kadar Yapilan Kritik Degisiklikler

### A) Hasta karti acilis davranisi (kullanici istegi)

Istegin ozeti:
- Hasta kartina tiklayinca **Hasta Takip Merkezi** acilsin.
- `.../hasta-dosyasi` otomatik acilmasin.

Yapilanlar:
- Hasta listesi kartlarinda tum acilis hedefleri `/hasta/<patient_key>` yapildi.
- Kart govdesi, avatar, isim ve `AÃ§` butonu bu hedefe alindi.
- JS tarafina normalize katmani eklendi:
  - Eski cache veya eski HTMLâ€™den `.../hasta-dosyasi` gelirse otomatik `.../hasta/<key>`e cevirir.
- Sunucu tarafina fallback yonlendirme eklendi:
  - `Referer: /hastalar` ile gelen `GET /hasta/<key>/hasta-dosyasi` isteklerinde `/hasta/<key>`e doner.

Dosya:
- `yazklinik_web.py`

### B) D700 service runner/lock davranisi

Yapilanlar:
- `D500_SERVICE_RUNNER.py` icinde lock/owner tespiti guclendirildi.
- Project `.venv` parent + Python312 child zinciri gecersiz lock owner sanilmasin diye tespit yumusatildi.
- Agresif lock takeover defaultta kapali tutuldu; sadece acikca etkinlestirilirse takeover denensin.

Dosya:
- `D500_SERVICE_RUNNER.py`

### C) Health monitor restart firtinasi azaltma

Yapilanlar:
- `D500_HEALTH_MONITOR.py` icinde web fail/restart davranisina koruma eklendi:
  - `FAIL_THRESHOLD` ve web/sip thresholdlari daha guvenli tabana cekildi.
  - Web hard-down senaryosunda bile tek failde restart yerine minimum 2 fail bekleme ayari yapildi.
- `config.env` icinde:
  - `YAZKLINIK_HEALTH_WEB_ENFORCE_MANAGED_OWNER=1` yapildi.

Dosyalar:
- `D500_HEALTH_MONITOR.py`
- `config.env`

---

## 3) Canli Durumdan Notlar (Onemli)

- Kart hedefleri dogrulandi:
  - `/hastalar` HTML icinde kart hedefleri `/hasta/<key>`
  - `.../hasta-dosyasi` kart hedefi bulunmadi.
- Kisa donemli web dalgalanmalari goruldu:
  - Bazi anlardaki kontrollerde `5052/5443` listener dusup geri gelme durumu oldu.
  - Health monitor logunda gecmiste tekrarli monitor start satirlari var.
- Son asamada uygulamayi ayakta tutmak icin dogrudan web start ile listener geri getirildi:
  - 5052 ve 5443 tekrar dinlemeye alinabildi.

Not:
- Bu durum â€œhasta karti tiklama davranisiâ€ duzeltmesinden ayri bir runtime stabilite problemi olarak ele alinmali.

---

## 4) Claudeâ€™dan Beklenen Sonraki Isler (Oncelik Sirasi)

### 1. Oncelik: Web flapping kok nedenini kalici cozum

Hedef:
- `5052/5443` portlari stabil kalsin.
- Health monitor restart dongusu olusmasin.

Bakilacaklar:
- `D500_HEALTH_MONITOR.py` log akisi ve restart tetikleme kosullari
- `D500_BASLAT.bat` icindeki monitor/web spawn paterni
- `runtime_state/service_locks/*.lock` ve `%TEMP%\YazKlinik\locks\web_5052.lock` senaryolari
- Ayni anda birden fazla monitor start olusup olusmadigi

### 2. Oncelik: Tek owner politikasini netlestir

Hedef:
- Web surecinin tek sahibi net olsun (runner ya da controlled direct run)
- Health monitor buna gore â€œmanage-ownerâ€ kararlarini tutarli versin

### 3. Oncelik: Login + hasta akisi smoke

Hedef:
- `giris -> hastalar -> kart tikla -> /hasta/<key>` akisi 100% stabil calissin

---

## 5) Dikkat Edilecek Kurallar (Proje Ici)

- `yazklinik_v68.py` dosyasina gereksiz dokunma.
- Hasta verisi silme yok (soft/archive mantigi).
- NAS altinda Python ile dosya silme yok.
- `git reset --hard` / `git checkout --` kullanma.
- f-string icindeki JS/CSS suzlu parantezlerde `{{` `}}` kacisina dikkat et.

---

## 6) Son Degisen Dosyalar (Bu devir kapsaminda kritik)

- `D:\YazKlinik_Final_D500\yazklinik_web.py`
- `D:\YazKlinik_Final_D500\D500_SERVICE_RUNNER.py`
- `D:\YazKlinik_Final_D500\D500_HEALTH_MONITOR.py`
- `D:\YazKlinik_Final_D500\config.env`

---

## 7) HÄ±zlÄ± Operasyon Komutlari

### Compile

```powershell
& "D:\YazKlinik_Final_D500\.venv\Scripts\python.exe" -m py_compile `
  "D:\YazKlinik_Final_D500\yazklinik_web.py" `
  "D:\YazKlinik_Final_D500\D500_SERVICE_RUNNER.py" `
  "D:\YazKlinik_Final_D500\D500_HEALTH_MONITOR.py"
```

### Quick check

```powershell
& "D:\YazKlinik_Final_D500\.venv\Scripts\python.exe" `
  "D:\YazKlinik_Final_D500\CODEX_QUICK_CHECK.py"
```

### Listener kontrol

```powershell
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in 5052,5443 } |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

### Loglar

```powershell
Get-Content "D:\YazKlinik_Final_D500\D500_server.log" -Tail 120
Get-Content "D:\YazKlinik_Final_D500\D500_server_HATA.log" -Tail 120
Get-Content "D:\YazKlinik_Final_D500\D500_health_monitor.log" -Tail 120
Get-Content "D:\YazKlinik_Final_D500\D500_health_monitor.err.log" -Tail 120
```

---

## 8) Kisa Sonuc

- Hasta karti tiklama hedefi istenen sekilde duzeltildi ve geriye donuk normalize/fallback katmanlari eklendi.
- Runtime stabilite icin monitor/runner tarafinda guvenlik yamalari atildi.
- Kalan ana risk: aralikli web listener dusmesi/flapping. Claude tarafinda kalici stabilizasyon odagi bunun uzerinde olmalÄ±.


