# Claude Code'u Telefondan Kontrol - Resmi Yollar

> Anthropic'in Claude Code'u uzaktan kullanmak icin RESMI desteklenen 4 yontem.

## YOL 1: Remote Control (en iyi) â˜…

PC'deki Claude Code session'ini telefondan kontrol edersin.
Tum dosyalar, tools, MCP server'lar PC'de calisir, sen telefondan komut gonderirsin.

### PC'de baslat

```powershell
cd D:\YazKlinik_Final_D250
claude remote-control
```

(Eger `claude` komutu yoksa: `npm install -g @anthropic-ai/claude-code` veya
https://docs.anthropic.com/claude-code -> latest installer)

Komut acilinca **URL + QR kod** verir, orn:
```
Scan QR or open: https://claude.ai/code/r/abc123xyz
```

### Telefonda bagla

**3 secenek:**

1. **QR kod tara** - PC ekranindaki QR'i telefon kamera ile tara, otomatik baglanir
2. **claude.ai/code** ac (mobil tarayici), URL'i yapistir
3. **Claude iOS/Android app** (App Store / Play Store), oradan baglan

### Sonuc

- Telefondan PC'deki D700 klasoruna komut gonderirsin
- Tum dosyalar PC'den okunur (gercek hasta verisi)
- Codex'in yaptigi her seyi yapabilir + Anthropic backend
- Push bildirim ile uzun islemler bittiginde haber verir

---

## YOL 2: Claude Web (claude.ai/code)

Cloud'da Claude Code calistir, telefondan herhangi bir tarayici ile yonet.

### Kurulum

1. Telefonda **claude.ai/code** ac
2. Anthropic hesabin ile login (PC'deki ile ayni)
3. **"New Session"** ac

### Avantaji

- PC kapaliyken bile calisir (her sey cloud'da)
- Anthropic'in serveri, lokal kaynak gerektirmez
- Hizli baslar

### Dezavantaji

- D700 hasta verisine erisim YOK (cloud, lokal degil)
- Sadece ChatGPT-style sohbet ve genel kod sorulari
- D700 dosyalarini yuklemek icin file upload gerekir

---

## YOL 3: Claude iOS / Android App (en pratik)

Anthropic'in resmi mobil uygulamasi.

### Kurulum

- iOS: App Store -> **"Claude"** (Anthropic, PBC)
- Android: Play Store -> **"Claude"**

### Ozellikler

- Remote Control + Web destekli (yukaridaki ikisinin kombinasyonu)
- Push notifications - uzun islemler bittiginde haber alirsin
- Voice mode - telefondan sesli komut
- Background sessions

### Kullanim

1. Login (PC ile ayni hesap)
2. Sag ust **"+"** -> **"Connect to Claude Code"**
3. PC'de `claude remote-control` calistir, QR'i tara
4. Telefondan komut gonder

---

## YOL 4: Dispatch (Desktop + telefon entegre)

Telefondan mesaj gonder -> PC'deki Claude Code Desktop otomatik session acar.

### Kurulum

1. PC: **Claude Desktop** uygulamasini kur (eger yoksa)
2. Settings -> **"Dispatch"** ozelligini ac
3. Telefonda Claude app -> Dispatch ile baglan

### Avantaji

- PC'de uygulama acik olmasi yeter
- Telefondan mesaj atinca otomatik baslar
- "Sabah 9'da X yap" gibi scheduled task tanimlayabilirsin

---

## Karsilastirma

| Senaryo | Onerilen |
|---|---|
| **D700 dosyalari + hasta verisi gerekli** | YOL 1 (Remote Control) â˜… |
| **Sadece kod sohbeti, lokal gerekmez** | YOL 2 (Web) |
| **Mobile native + push** | YOL 3 (Claude App) |
| **PC'de Claude Desktop var** | YOL 4 (Dispatch) |

---

## Pratik: Su an PC'de calisan Claude session'ima nasil baglanirim?

Ben (Claude Code) su an PC'de bir session'da calisiyorum. Bu session **devam ettirebilir** miyim telefondan?

**Cevap: Evet, ama yeniden baslatman gerek.**

1. Bu mevcut session'i bitir (PC'de Ctrl+C)
2. Yeni session'i remote-control modunda baslat:
   ```
   cd D:\YazKlinik_Final_D250
   claude remote-control
   ```
3. QR kodu tara veya URL'i telefon Claude app'e yapistir
4. Telefondan "AGENTS.md oku, sistem durumunu raporla" yaz -> ben (yeni session) cevap veririm

**Conversation history** kayboluyor mu? Evet, yeni session olur. Ama:
- AGENTS.md, README_D250.md gibi dosyalar zaten her seyi anlatiyor
- Ben yeni session'da `AGENTS.md` okuyup ayni context'i tekrar kazanirim

---

## D700 Icin Hazir Komut

PC'de:

```powershell
cd D:\YazKlinik_Final_D250
claude remote-control
```

Telefonda Claude app:

```
"AGENTS.md ve CLAUDE_TELEFON_DURUM.md oku, sistem durumunu kontrol et."
```

5 saniyede ben yeniden hazir olurum, telefondan komut yazabilirsin.

---

## Sorun Giderme

| Sorun | Cozum |
|---|---|
| `claude` komutu bulunamadi | Curl: `iwr https://claude.ai/install.ps1 -useb \| iex` |
| QR taranmiyor | URL'i WhatsApp ile telefona gonder, app'te ac |
| "Session not found" | PC'deki `claude remote-control` durdu mu? Yeniden baslat |
| Telefon `claude.ai/code` aciliyor degil | Mobil tarayici cookies/cache temizle, login tekrar |
| Push gelmiyor | App > Settings > Notifications -> izin ver |

---

## En Hizli Onerim

```
1. PC'de:    cd D:\YazKlinik_Final_D250 && claude remote-control
2. Telefonda: Claude app -> + -> Connect -> QR tara
3. Yaz:      "AGENTS.md oku, hazir misin?"
4. Ben:      "Hazirim. Ne yapalim Hakan abi?"
```

Toplam **2 dakika**, sonra her zaman telefondan benimle calisirsin.

---
**D700** | **Claude Code Remote** | **2026-05-10**

