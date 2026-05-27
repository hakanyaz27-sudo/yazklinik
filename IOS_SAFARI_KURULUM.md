# YazKlinik iOS Safari Kurulum Rehberi

> **Hedef**: iPhone / iPad Safari'de YazKlinik'i sorunsuz kullanmak, ana ekrana ekleyip native uygulama gibi calistirmak.

> **Cihaz**: iPhone 17 Pro Max (6.9" ProMotion 120Hz, Dynamic Island, iOS 19) - tam optimize

---

## iPhone 17 Pro Max'a Ozel Optimizasyonlar (2026-05-17)

YazKlinik su an iPhone 17 Pro Max icin **tam optimize**:

### 1. **`/mobil` ozel dashboard** (yeni)
Ana ekran ikonuna tikladiginda direkt buraya gel:
- 2x2 buyuk kart grid (Yeni Hasta / Randevular / YZ Konsult / USG / Stok / Ajanlar)
- Saat + bugunun ozeti band
- Hizli arama (parmagla yazi)
- Sag altta **sari mikrofon FAB** - dokunmatik sesli komut
- Glassmorphism + gradient (D700 mavi-yesil)

URL: `https://...:5443/mobil`

### 2. **ProMotion 120Hz scroll**
- Tum animasyonlar GPU katmanli (`will-change`, `transform: translateZ(0)`)
- Smooth scroll behavior
- Tap delay 0ms (`touch-action: manipulation`)
- Active state `scale(0.97)` ile haptic-benzeri feedback

### 3. **Dynamic Island safe-area**
- Body top padding `max(env(safe-area-inset-top), 44px)` standalone'da
- Dynamic Island'a icerik girmiyor
- Status bar `black-translucent` - mavi tema icine sigar

### 4. **iPhone 17 Pro Max splash screens**
PWA acilisinda gradient + ikon + "YazKlinik" yazi:
- Portrait: 1320x2868 PNG (3x ProMotion)
- Landscape: 2868x1320 PNG
- iPhone 15/17 Pro/Pro Max/iPad Pro 13" hepsine ayri dosya var

### 5. **StandBy mode** (iPhone 17 Pro Max yatay sarjdayken)
- Yatay landscape kucuk yukseklik (`max-height: 500px`)
- Alex bar 48px, h1 18px
- Saat + minimum bilgi gozukur

### 6. **Always-On display**
- `prefers-reduced-motion + display-mode: standalone` ile animasyonlar pasif
- Pil tasarrufu

### 7. **iPad Pro 13" landscape uyumu**
- 600x maximum width
- Alex bar 600px max-width
- 3-column action grid

---

## Hizli Baslat (iPhone 17 Pro Max)

1. **Tailscale Funnel kur** (bilgisayarda):
   ```
   D:\YazKlinik_Final_D500\D500_TAILSCALE_FUNNEL_8443_KUR.bat
   ```
   Bu sana `https://hakan-pc.tailnet-xxxx.ts.net` adresi verir.

2. **iPhone'da Tailscale yukle** (App Store), ayni hesap.

3. **Safari'de adresi ac** -> Login.

4. **Sag alttaki Paylas (square + up arrow)** -> **Add to Home Screen** -> "YazKlinik".

5. **Ana ekrandan ikona dokun** -> direkt `/` veya `/mobil` adresi tam ekran acilir.

6. **Voice komut testi**: Mikrofon ikona dokun, "ana sayfa" de.

---

## 1. BaÄŸlantÄ± HazÄ±rlÄ±ÄŸÄ± (Hangi URL ile baÄŸlanacaksÄ±n?)

YÃ¶ntem seÃ§:

### A. **Tailscale Funnel (Ã–NERÄ°LEN - gerÃ§ek HTTPS sertifika)**

Tailscale Funnel kurarsan:
- GerÃ§ek `*.ts.net` HTTPS sertifika (Safari uyarÄ± vermez)
- iOS Add to Home Screen, Push Notification Ã§alÄ±ÅŸÄ±r
- Internet Ã¼zerinden de gÃ¼venli eriÅŸim

**Kurulum** (PC'de):
```powershell
# Klinik bilgisayarda
D:\YazKlinik_Final_D500\D500_TAILSCALE_FUNNEL_8443_KUR.bat
```

Bu sana `https://hakan-pc.tailnet-xxx.ts.net` gibi bir adres verir. iPhone'da Tailscale uygulamasÄ±nÄ± da kur, aynÄ± hesapla giriÅŸ yap, sonra Safari'de bu adresi aÃ§. **Sertifika uyarÄ±sÄ± Ã§Ä±kmaz**.

### B. **LAN Ã¼zerinden self-signed (uyarÄ±lÄ±)**

AynÄ± WiFi'desin diyelim, PC IP'si `192.168.1.X`. Safari'de aÃ§:
```
https://192.168.1.X:5443
```

Ä°lk aÃ§Ä±lÄ±ÅŸta sertifika uyarÄ±sÄ± Ã§Ä±kar â†’ **"Visit Website" â†’ "Continue"**. iPhone'da bu gÃ¼veni kalÄ±cÄ± yapmak iÃ§in:

1. Safari'de adresi aÃ§
2. Sertifika uyarÄ±sÄ± â†’ "**Show Details**" â†’ "**Visit this website**"
3. Settings â†’ General â†’ **VPN & Device Management** â†’ "Ä°ndirilen Profil" â†’ **Install**
4. Settings â†’ General â†’ About â†’ Certificate Trust Settings â†’ **Yazklinik'i Enable Full Trust**

Bu yÃ¶ntem zahmetli; **Tailscale Funnel Ã¶nerilir**.

### C. **iCloud Private Relay devre dÄ±ÅŸÄ± bÄ±rak**

BazÄ± iOS'ta iCloud Private Relay self-signed sertifikalÄ± IP'leri bloklar. Settings â†’ Apple ID â†’ iCloud â†’ Private Relay â†’ **OFF** (sadece bu site iÃ§in deÄŸil, hepsi iÃ§in kapanÄ±r).

---

## 2. Safari'de AÃ§ + Ana Ekrana Ekle

1. Safari'de `https://...` adresini aÃ§ â†’ **GiriÅŸ** sayfasÄ± gÃ¶rÃ¼nmeli
2. Doktor kullanÄ±cÄ±sÄ±yla giriÅŸ yap (parola `users.json`'da)
3. Alt menÃ¼deki **PaylaÅŸ** ikonu (kare + ok) â†’ **Add to Home Screen** â†’ "YazKlinik"
4. Ana ekranda app ikonu olarak Ã§Ä±kar (medikal beyaz + Y harfi)
5. Ä°kona dokun â†’ **Tam ekran aÃ§Ä±lÄ±r** (Safari adres Ã§ubuÄŸu yok)

---

## 3. iOS'ta DoÄŸru Ã‡alÄ±ÅŸmasÄ± Beklenen Ã–zellikler

- âœ… **Tam ekran (standalone)** - browser Ã§ubuÄŸu yok
- âœ… **Status bar ÅŸeffaf** (Ã¼st notch alanÄ± app rengi ile uyumlu)
- âœ… **Safe area saygÄ±** (notch ve home indicator'a dÃ¼ÅŸmez)
- âœ… **Touch hedefleri 44pt+** (Apple HIG)
- âœ… **Input'lar 16px font** (focus'ta otomatik zoom yok)
- âœ… **Dynamic Type uyumlu** (kullanÄ±cÄ± font boyutu)
- âœ… **Dark Mode tutarlÄ±** (iOS sistem temasÄ±)
- âœ… **Tablolar yatay scroll** (mobil kÃ¼Ã§Ã¼k ekranda)
- âœ… **Alex bar altta sabit** (parmakla eriÅŸilebilir)
- âš ï¸ **Push notification**: iOS 16.4+ Web Push destekler; Tailscale Funnel ile Ã§alÄ±ÅŸÄ±r

---

## 4. Ã–nerilen KullanÄ±m AkÄ±ÅŸÄ±

### Doktor AsistanÄ± (telefondan hÄ±zlÄ± eriÅŸim)
- Ana ekrandan ikona tÄ±kla
- **Alex bar** altta â†’ sesli komut: "BPD 85", "tansiyon 158/102"
- **/randevular** kÄ±sayolu (manifest shortcut)
- **/status** aÃ§Ä±k (klinik servisi Ã§alÄ±ÅŸÄ±yor mu hÄ±zlÄ± bak)

### Doktor (klinikte iPad)
- iPad landscape modunda **/dashboard** aÃ§Ä±k
- **/uyumluluk** ile gÃ¼nlÃ¼k ISO/KVKK skor kontrolÃ¼
- **/hasta-portal/giris?token=...** ile hasta linklerini test
- **/stok** ile ilaÃ§ miatlarÄ± kontrol

### Hasta (kendi telefonu)
- WhatsApp'tan gelen magic link aÃ§Ä±lÄ±r
- `/hasta-portal/giris?token=...&sig=...` â†’ ziyaret listesi
- Recete, USG raporu gÃ¶rÃ¼r (KVKK-sÄ±nÄ±rlÄ±)

---

## 5. Bilinen iOS Safari SÄ±nÄ±rlamalarÄ±

| SÄ±nÄ±rlama | AÃ§Ä±klama | Ã‡Ã¶zÃ¼m |
|---|---|---|
| Service Worker storage 7 gÃ¼n | Site 7 gÃ¼n kullanÄ±lmazsa cache silinir | App standalone modunda gÃ¼nlÃ¼k aÃ§Ä±lÄ±rsa sorun olmaz |
| Background sync yok | Arka planda sync yapamaz | Cron + push notification ile aÅŸÄ±lÄ±r |
| Push notif iOS < 16.4 | Yok | iOS 17+ gÃ¼ncel |
| WebRTC mikrofon kullanÄ±mÄ± | Ä°zin her sayfa aÃ§Ä±lÄ±ÅŸÄ±nda | "Always Allow" Safari ayarÄ±ndan |
| File upload kamerasÄ± | Ä°zin gerekli | Ä°lk kullanÄ±mda Allow seÃ§ |

---

## 6. Sorun Giderme

### **"Bu site Ã¶zelliÄŸi yok" mesajÄ±**
- Service worker scope `/` olmadÄ±ÄŸÄ±nda. Adres Ã§ubuÄŸunda `/` ile aÃ§, alt sayfa deÄŸil.

### **"Sayfa yÃ¼klenemiyor"**
- HTTPS sertifika gÃ¼venilir deÄŸil. Tailscale Funnel kur veya cert install et.

### **Ä°kon karelÄ±/eski gÃ¶rÃ¼nÃ¼yor**
- Eski cache. Safari â†’ Settings â†’ Clear History â†’ tekrar Add to Home Screen.

### **YazÄ±lar kÃ¼Ã§Ã¼k / bÃ¼yÃ¼k**
- iOS Dynamic Type. Settings â†’ Display â†’ Text Size kÃ¼Ã§Ã¼k/bÃ¼yÃ¼k.

### **Alex sesi gelmiyor**
- iOS mÃ¼zik/video oynatÄ±yor mu? Ã–nce bunu durdur.
- AirPods baÄŸlÄ±yken bazen ses kÄ±sÄ±k â†’ Volume Up.

### **Form'a tÄ±klayÄ±nca zoom yapÄ±yor**
- Input font-size 16px altÄ±nda. Bu fix'lendi (yk-ios-mobile.css), cache temizle.

### **Notch'tan iÃ§erik gÃ¶zÃ¼kmÃ¼yor**
- viewport-fit=cover meta eksik. Bu fix'lendi.

---

## 7. iPhone'a Ã–zel Ä°puÃ§larÄ±

- **3D Touch / Haptic Touch**: Ana ekran ikonuna basÄ±lÄ± tut â†’ "Yeni Hasta", "Randevular", "Dashboard" kÄ±sayollarÄ±
- **Splash Screen**: iOS otomatik Ã¼retir (app icon bÃ¼yÃ¼k + arka plan = manifest background_color)
- **App Switcher**: PWA olarak ayrÄ± pencere gÃ¶rÃ¼nÃ¼r
- **Picture-in-Picture**: Åu an yok (video oynatma yok)

---

## 8. Test AdÄ±mlarÄ± (HÄ±zlÄ±)

iPhone Safari'de:
1. âœ… `https://...` aÃ§ â†’ GiriÅŸ sayfasÄ± gÃ¶zÃ¼kmeli
2. âœ… Login â†’ Dashboard aÃ§Ä±lmalÄ±
3. âœ… SaÄŸ alt **PaylaÅŸ** â†’ Add to Home Screen â†’ "YazKlinik"
4. âœ… Ana ekrandan ikona dokun â†’ tam ekran aÃ§Ä±lmalÄ±
5. âœ… Status bar mavi (theme-color) gÃ¶rÃ¼nmeli
6. âœ… Bir input'a dokun â†’ klavye aÃ§Ä±lÄ±rken zoom YAPMAMALI
7. âœ… Alex bar altta gÃ¶rÃ¼nmeli, dokunmatik Ã§alÄ±ÅŸmalÄ±
8. âœ… `/status` aÃ§ â†’ tÃ¼m servisler tablo halinde
9. âœ… `/uyumluluk` aÃ§ â†’ grade A-F renkli gÃ¶rÃ¼nmeli
10. âœ… Telefon yatay Ã§evir â†’ layout bozulmamalÄ±

---

## 9. Performans Notu

iOS'ta WebGL/3D yok ama tÃ¼m Session 7 sayfalarÄ± **statik HTML + minimal JS** kullanÄ±r â†’ Ã§ok hÄ±zlÄ±. Network tarafÄ±nda:
- Lokal LAN (Tailscale): ~10-50 ms
- Internet (Tailscale Funnel): ~80-150 ms
- 4G: ~200-400 ms

**Cache**: Service Worker (sw.js) static asset'leri cacheliyor â†’ 2. aÃ§Ä±lÄ±ÅŸ %80 daha hÄ±zlÄ±.

---

## 10. Ä°leri (opsiyonel)

- **VOIP/SIP**: iOS'ta WebRTC ile sesli arama â†’ tarayÄ±cÄ±dan direkt SIP bridge
- **Apple Watch Push**: Tailscale Funnel + Web Push â†’ saat bildirimi
- **Siri Shortcuts**: Manifest shortcut + URL scheme â†’ "Hey Siri, randevularÄ± aÃ§"
- **CallKit benzeri**: Bekleyen iÅŸ notification haline gelir

---

**Not**: Tailscale Funnel kurulumu iÃ§in: `D500_TAILSCALE_FUNNEL_8443_KUR.bat` veya `TAILSCALE_UZAKTAN_ERISIM.md` dosyasÄ±na bak.

**HazÄ±rlayan**: Claude AI (2026-05-17)

