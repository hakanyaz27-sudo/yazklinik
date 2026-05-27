# Telefondan Claude ile YazKlinik D700'u Kontrol - 3 Yol

## YOL 1: Claude.ai Project (en pratik) â˜…

### Kurulum (1 kez, 5 dakika)

1. Telefonda **Claude app** veya tarayicidan **claude.ai** ac
2. Sol ust **"Projects"** > **"New Project"**
3. Proje adi: **"YazKlinik D700"**
4. **Project Knowledge** (alt boluk) > **"Add content"**
5. Su 5 dosyayi yukle (PC'den telefonuna OneDrive/WhatsApp ile gonder, sonra yukle):
   - `AGENTS.md` (~10 KB)
   - `README_D250.md`
   - `CODEX_FILE_MAP.md`
   - `CODEX_API_ENDPOINTS.md`
   - `CLAUDE_TELEFON_DURUM.md`
6. **Custom Instructions** kismina yapistir:

```
Bu proje: YazKlinik Pro Final D700 - Op. Dr. Hakan YAZ (Kadin Dogum) icin Flask/Python klinik yonetim sistemi.
Klasor: D:\YazKlinik_Final_D250\
Kullanici Turkce konusur, kisa cevap ister.
"Yap" deyince: kod + test + 1 cumle teslim.
v68.py dokunma kuralina uy. Hasta verisi silme.
```

### Kullanim

Telefonda Claude > **"YazKlinik D700" project** ac > sor:

- "Hasta birlestir route nasil calisiyor?"
- "Sistem ayarlari sayfasinda hangi env var'lar var?"
- "DDI kurallarinin tamamini listele"
- "Yeni bir route eklemek istesem nereye yazarim?"

Claude tum dokumantasyonu hatirladigi icin direkt cevap verir.

---

## YOL 2: PC'deki sayfayi telefonda ac (Tailscale / LAN)

### Ayni WiFi'deyken (kolay)

Telefonda ayni WiFi'a bagliyken **mobil tarayicidan** ac:
```
http://192.168.1.40:5052
```
veya HTTPS:
```
https://192.168.1.40:5443
```

Giris: `doktor / 1234`

> Tum klinik moduller, hasta listesi, tedavi planlayici, sistem ayarlari telefondan da kullanilabilir (responsive UI).

### Disardan (3G/4G ile) - Tailscale (ucretsiz)

1. PC'ye **Tailscale** kur (https://tailscale.com/download/windows)
2. Telefon icin Tailscale uygulamasini Play Store / App Store'dan kur
3. Ikisinde de ayni Google/Microsoft hesabi ile giris yap
4. PC bir Tailscale IP alir (orn. `100.71.108.26`)
5. Telefondan ac:
```
http://100.71.108.26:5052
```

> Avantaj: VPN gibi calisir, internetten guvenli erisim. Klinik LAN'dan disarida da.

---

## YOL 3: Claude in Chrome ile uzaktan kontrol

### Mobil Chrome'da Claude extension

1. **Claude in Chrome extension** kur (Chrome Web Store)
2. Telefondan ac:
```
http://192.168.1.40:5052/sistem-durumu
```
3. Claude extension'a sor: "Bu sayfada ne goruyorsun?"
4. Claude extension sayfayi okur, sana ozet verir, butonlara basabilir

### Avantaji

Claude **canli sayfayi** gorur (hasta listesi, sistem durumu vs).
Telefonda kucuk ekrandayken Claude orta katmanda calisir.

---

## Hizli Karsilastirma

| Yol | Zorluk | Internet | Avantaj |
|---|---|---|---|
| **1. Claude Project** | Kolay | Var | Dokuman bazli, surekli erisim |
| **2. LAN/Tailscale** | Orta | LAN/VPN | Canli sistem, gercek hasta verisi |
| **3. Claude in Chrome** | Orta | Var | Hibrit - hem dokuman hem canli |

---

## Onerim

**Once YOL 1** kur (5 dakika, sonra hep islerine yarar).
Acil hasta verisi gerekiyorsa **YOL 2** (Tailscale).

## Dosyalari telefona nasil gonderirsin

PC'de PowerShell:
```powershell
# Bu 5 dosyayi OneDrive'a kopyala (telefonda OneDrive uygulamasi acar)
$dst = "C:\Users\yazha\OneDrive\YazKlinik_Telefon"
New-Item -ItemType Directory -Path $dst -Force | Out-Null
Copy-Item "D:\YazKlinik_Final_D250\AGENTS.md" $dst -Force
Copy-Item "D:\YazKlinik_Final_D250\README_D250.md" $dst -Force
Copy-Item "D:\YazKlinik_Final_D250\CODEX_FILE_MAP.md" $dst -Force
Copy-Item "D:\YazKlinik_Final_D250\CODEX_API_ENDPOINTS.md" $dst -Force
Copy-Item "D:\YazKlinik_Final_D250\CLAUDE_TELEFON_DURUM.md" $dst -Force
Copy-Item "D:\YazKlinik_Final_D250\CLAUDE_TELEFON_REHBER.md" $dst -Force
Write-Output "5 dosya OneDrive'a kopyalandi - telefonda OneDrive klasorunde gor"
```

Telefonda **OneDrive uygulamasi** > **YazKlinik_Telefon** klasoru > 5 dosyayi gor + Claude projeye yukle.

---
**D700** | **Op. Dr. Hakan YAZ** | **2026-05-10**

