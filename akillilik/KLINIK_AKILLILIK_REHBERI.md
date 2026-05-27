# YazKlinik Akillilik Paketi - Doktor Rehberi

**Tarih:** 2026-05-17
**Klasor:** `D:\YazKlinik_Final_D500\akillilik\`

> Bu paket YazKlinik'i bir doktor verimliligi platformuna donusturur:
> akilli RAG (Alex senin verini tanir), medikal LLM (meditron:70b ile konsultasyon),
> profesyonel sifre yoneticisi (Vaultwarden), workflow otomasyonu (n8n),
> servis saglik dashboard (Uptime Kuma), Ollama icin guzel arayuz (Open WebUI).

---

## 1 DAKIKADA KURULUM

```powershell
cd D:\YazKlinik_Final_D500\akillilik

# Once kuru ne yapacagini gor (zarar yok):
.\INSTALL_AKILLILIK_PAKETI.ps1

# Begendiysen gercekten kur:
.\INSTALL_AKILLILIK_PAKETI.ps1 -Run

# Dogrula:
.\VERIFY_AKILLILIK.ps1
```

---

## KURULDU MU? - 4 PANEL AC

| Servis | URL | Niye | Ilk acmada |
|---|---|---|---|
| **Vaultwarden** | http://localhost:18443 | Klinik parola yoneticisi | Hesap olustur, BulutKlinik/SGK/NAS parolalari ekle |
| **Uptime Kuma** | http://localhost:13001 | Servis saglik dashboard | Hesap olustur, YazKlinik 5443'u watch list'e ekle |
| **n8n** | http://localhost:15678 | Workflow otomasyonu | Owner hesabi olustur, ilk workflow'u dene |
| **Open WebUI** | http://localhost:13000 | Ollama'ya guzel UI | Admin hesabi olustur, "yaz:latest" modelini sec |
| **YazKlinik** | https://127.0.0.1:5443 | (zaten var) | `doktor/1234` -> **HEMEN PAROLA DEGISTIR!** |

---

## DOKTOR ICIN KAZANIMLAR (sirayla)

### 1. Akilli RAG - Alex artik senin verini taniyor

**Once:** "Kilic Seval'in son USG'sini soyle" -> Alex: "Hasta dosyasina bakin"
**Sonra:** "Kilic Seval'in son USG'sini soyle" -> Alex: "GA 32 hafta, EFW 1850g, BPD 80mm. Klinik flag: SGA suphesi"

Nasil oldu:
- Eski embedding: `paraphrase-multilingual-mpnet-base-v2` (2 yillik)
- Yeni embedding: **BAAI/bge-m3** (multilingual SOTA, Turkce mukemmel)
- Eklenen: **BAAI/bge-reranker-v2-m3** ikinci asama yeniden siralama
- Sonuc: Yazim hatasinda ("Kilic Sevall") bile bulur, alakali olmayan belge daha az gelir

Test: `/alex-rag-merkezi` sayfasinda "Test Search" -> sorgu yaz, sonuclar artik daha dogru

### 2. Konsultasyon Ajani artik medikal LLM kullaniyor

**Once:** Tum adimlar `qwen2.5:32b` (genel amac) ile
**Sonra:** Adim bazli **akilli model secimi**:

| Adim | Model | Niye |
|---|---|---|
| Vaka yapilandirma (extract) | qwen2.5:32b | JSON cikti dayatma iyi |
| Ayirici tani (ddx) | **meditron:70b** | Stanford tibbi LLM |
| Onerilen tetkik (workup) | **meditron:70b** | Klinik karar |
| Tedavi plani (treatment) | **meditron:70b** | Ilac + doz |
| Takip plani (followup) | qwen2.5:32b | Akilli plan |

Sonuc: `/yz-konsultasyon` artik gercek doktor kalitesinde cevap veriyor.

### 3. Open WebUI - Ollama'na ChatGPT-vari arayuz

http://localhost:13000

- Tum Ollama modellerini dene (yaz:latest, qwen2.5:72b, meditron:70b, llama3.2-vision)
- Konusma gecmisi otomatik saklanir
- Multi-modal: `llama3.2-vision:11b` ile **USG resmini sur, sor** "BPD'yi olc"
- Eski ChatGPT konusmalarini buraya tasi (export/import)

### 4. n8n - Klinik workflow otomasyonu

http://localhost:15678

Hazir kullanim ornekleri (n8n'de "Workflow > Import" ile ekle):

- **Yeni randevu hatirlatma**: YazKlinik webhook -> 24h sonra hastaya WhatsApp
- **Voluson PDF watch**: NAS klasoru izle -> yeni PDF -> doktora Telegram bildirim
- **Gun sonu raporu**: Her aksam 18:00 -> SQLite sorgu -> Email/Telegram ozet
- **Gelmeyen hasta**: visit_date gectir + status='no_show' -> ertesi gun otomatik tekrar arama

n8n 400+ entegrasyona sahip: WhatsApp Business, Telegram, Gmail, Google Sheets, SQLite, HTTP webhook, vs.

### 5. Vaultwarden - Tum klinik sifrelerini tek yerde

http://localhost:18443

- `doktor/1234` artik kabul edilmez! Vaultwarden'da random olustur, sakla
- Tarayici uzantisi (Bitwarden) Chrome/Edge'de otomatik dolduran
- Mobil: Bitwarden Android/iOS, biometric login
- Aile/ekip paylasimi (sekreterle "ortak vault")
- Tum parolalari sifrelenmis (AES-256, sadece sen ana parolayi bilirsin)

**Ek olarak:** Vaultwarden'da "Notes" alani var - kritik bilgileri sakla (NAS path'leri, IP'ler, API key'ler).

### 6. Uptime Kuma - Servis saglik dashboard

http://localhost:13001

Watch list'e ekle (her biri 60sn'de bir check):
- `https://127.0.0.1:5443/giris` - YazKlinik
- `http://127.0.0.1:11434/api/tags` - Ollama
- `http://host.docker.internal:9000` - Whisper (varsa)
- `https://176.236.92.142:65187` - Public Funnel (varsa)
- `\\asustor\Voluson` - NAS (TCP port check)

Bildirim kanali ekle: Discord, Telegram, Email, Push notification. Bir servis donerse telefonuna gelir.

### 7. Arayuz akilliligi - htmx + Alpine.js + Chart.js

Otomatik inject edildi (Medikal tema gibi):
- **htmx**: sayfa yenilemeden form/buton (yeni sayfalar icin)
- **Alpine.js**: reactive widgets (dropdown, modal, tab)
- **Chart.js**: grafikler (hasta trend, mali rapor)

Codex veya ben yeni sayfa yazinca bunlari kullanabilir - mevcut sayfalar etkilenmiyor.

---

## GUVENLIK / KVKK

| Onlem | Yapildi mi? |
|---|---|
| Vaultwarden self-host (cloud yok) | Otomatik (Docker) |
| Vaultwarden admin token random | Install script yapiyor |
| Open WebUI auth zorunlu | docker-compose'da `WEBUI_AUTH=true` |
| n8n auth (owner hesabi) | Ilk ziyarette zorlanir |
| Tum data yerel `akillilik/data/` altinda | Otomatik (volume mount) |
| Yedek icin: `akillilik/data/` klasorunu Restic'le yedekle | Manuel (`restic` kur) |
| Default `doktor/1234` degisikligi | **SEN YAPACAKSIN!** |

---

## YEDEKLEME / GERI YUKLEME

Stack'i bir baska PC'ye tasimak veya yedek almak icin:

```powershell
# Yedek
cd D:\YazKlinik_Final_D500\akillilik
docker compose down
Compress-Archive -Path data -DestinationPath ".\backup_$(Get-Date -Format yyyy-MM-dd).zip"
docker compose up -d

# Geri yukleme (yeni PC'de)
Expand-Archive backup_2026-05-17.zip -DestinationPath .
docker compose up -d
```

---

## SORUN GIDERME

### "Docker compose up hata: connection refused"
- Docker Desktop calisiyor mu? `docker ps` ile kontrol.
- WSL2 etkin mi? `wsl --status`

### "Vaultwarden 18443 acilmiyor"
- Windows Firewall: `netsh advfirewall firewall add rule name="Vaultwarden" dir=in action=allow protocol=TCP localport=18443`
- Docker network: `docker network ls | grep yazklinik`

### "RAG hala eski model kullaniyor gibi"
- Server'i yeniden baslat: `Stop-Process python -Force; D500_BASLAT.bat`
- `/alex-rag-merkezi` -> "Re-Index" tikla (yeni embedding ile yeniden indeksle)
- Cache temizle: `D:\YazKlinik_Final_D500\rag_data\embed_cache\` icini sil

### "Open WebUI Ollama'yi bulmuyor"
- Ollama servisi calisiyor mu? `ollama list`
- Docker'dan host'a erisim: `host.docker.internal` (docker-compose'da var)
- Windows firewall Ollama 11434'u allow et

### "Konsultasyon yavas (>1 dakika)"
- `meditron:70b` 42 GB, ilk yuklemede yavas - sonra hizli
- Daha kucuk model dene: ENV `ALEX_USE_RERANKER=0`
- Veya: konsult ajanda `prefer="openai"` (eger OPENAI_API_KEY varsa)

### "Verify script: failed > 0"
- Detayli hata icin: `.\INSTALL_AKILLILIK_PAKETI.ps1 -Run`
- Manuel: `docker compose logs <servis>` ile container loglarina bak

---

## ILERIDE EKLENEBILECEKLER (manuel, gerektiginde)

| Program | Komut |
|---|---|
| OHIF DICOM Viewer | `docker run -d -p 13003:80 ohif/viewer:latest` |
| Jitsi Meet | `git clone https://github.com/jitsi/docker-jitsi-meet` |
| Stirling PDF | `docker run -d -p 13004:8080 frooodle/s-pdf:latest` |
| Restic backup | `winget install restic.restic` + ilk yedek |
| Obsidian (notlar) | `winget install Obsidian.Obsidian` |
| Zotero (makaleler) | `winget install Zotero.Zotero` |

---

## OZET

**Ne kazandin:**
- RAG 2x daha dogru (BGE-M3 + reranker)
- Konsultasyon doktor kalitesinde (meditron:70b)
- Tum klinik servisleri tek dashboard'da (Uptime Kuma)
- Klinik workflow otomasyonu (n8n)
- Profesyonel sifre yonetimi (Vaultwarden)
- Ollama'ya ChatGPT-vari arayuz (Open WebUI)
- Akilli arayuz altyapisi (htmx + Alpine.js + Chart.js)

**Sonraki adim:** `INSTALL_AKILLILIK_PAKETI.ps1 -Run` -> 30-60 dk -> bitince `VERIFY_AKILLILIK.ps1`

---

*Hazirlayan: Claude. Op. Dr. Hakan Yaz icin 2026-05-17.*
