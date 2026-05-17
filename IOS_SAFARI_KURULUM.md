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
- Glassmorphism + gradient (D300 mavi-yesil)

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
   D:\YazKlinik_Final_D300\D300_TAILSCALE_FUNNEL_8443_KUR.bat
   ```
   Bu sana `https://hakan-pc.tailnet-xxxx.ts.net` adresi verir.

2. **iPhone'da Tailscale yukle** (App Store), ayni hesap.

3. **Safari'de adresi ac** -> Login.

4. **Sag alttaki Paylas (square + up arrow)** -> **Add to Home Screen** -> "YazKlinik".

5. **Ana ekrandan ikona dokun** -> direkt `/` veya `/mobil` adresi tam ekran acilir.

6. **Voice komut testi**: Mikrofon ikona dokun, "ana sayfa" de.

---

## 1. Bağlantı Hazırlığı (Hangi URL ile bağlanacaksın?)

Yöntem seç:

### A. **Tailscale Funnel (ÖNERİLEN - gerçek HTTPS sertifika)**

Tailscale Funnel kurarsan:
- Gerçek `*.ts.net` HTTPS sertifika (Safari uyarı vermez)
- iOS Add to Home Screen, Push Notification çalışır
- Internet üzerinden de güvenli erişim

**Kurulum** (PC'de):
```powershell
# Klinik bilgisayarda
D:\YazKlinik_Final_D300\D300_TAILSCALE_FUNNEL_8443_KUR.bat
```

Bu sana `https://hakan-pc.tailnet-xxx.ts.net` gibi bir adres verir. iPhone'da Tailscale uygulamasını da kur, aynı hesapla giriş yap, sonra Safari'de bu adresi aç. **Sertifika uyarısı çıkmaz**.

### B. **LAN üzerinden self-signed (uyarılı)**

Aynı WiFi'desin diyelim, PC IP'si `192.168.1.X`. Safari'de aç:
```
https://192.168.1.X:5443
```

İlk açılışta sertifika uyarısı çıkar → **"Visit Website" → "Continue"**. iPhone'da bu güveni kalıcı yapmak için:

1. Safari'de adresi aç
2. Sertifika uyarısı → "**Show Details**" → "**Visit this website**"
3. Settings → General → **VPN & Device Management** → "İndirilen Profil" → **Install**
4. Settings → General → About → Certificate Trust Settings → **Yazklinik'i Enable Full Trust**

Bu yöntem zahmetli; **Tailscale Funnel önerilir**.

### C. **iCloud Private Relay devre dışı bırak**

Bazı iOS'ta iCloud Private Relay self-signed sertifikalı IP'leri bloklar. Settings → Apple ID → iCloud → Private Relay → **OFF** (sadece bu site için değil, hepsi için kapanır).

---

## 2. Safari'de Aç + Ana Ekrana Ekle

1. Safari'de `https://...` adresini aç → **Giriş** sayfası görünmeli
2. Doktor kullanıcısıyla giriş yap (parola `users.json`'da)
3. Alt menüdeki **Paylaş** ikonu (kare + ok) → **Add to Home Screen** → "YazKlinik"
4. Ana ekranda app ikonu olarak çıkar (medikal beyaz + Y harfi)
5. İkona dokun → **Tam ekran açılır** (Safari adres çubuğu yok)

---

## 3. iOS'ta Doğru Çalışması Beklenen Özellikler

- ✅ **Tam ekran (standalone)** - browser çubuğu yok
- ✅ **Status bar şeffaf** (üst notch alanı app rengi ile uyumlu)
- ✅ **Safe area saygı** (notch ve home indicator'a düşmez)
- ✅ **Touch hedefleri 44pt+** (Apple HIG)
- ✅ **Input'lar 16px font** (focus'ta otomatik zoom yok)
- ✅ **Dynamic Type uyumlu** (kullanıcı font boyutu)
- ✅ **Dark Mode tutarlı** (iOS sistem teması)
- ✅ **Tablolar yatay scroll** (mobil küçük ekranda)
- ✅ **Alex bar altta sabit** (parmakla erişilebilir)
- ⚠️ **Push notification**: iOS 16.4+ Web Push destekler; Tailscale Funnel ile çalışır

---

## 4. Önerilen Kullanım Akışı

### Doktor Asistanı (telefondan hızlı erişim)
- Ana ekrandan ikona tıkla
- **Alex bar** altta → sesli komut: "BPD 85", "tansiyon 158/102"
- **/randevular** kısayolu (manifest shortcut)
- **/status** açık (klinik servisi çalışıyor mu hızlı bak)

### Doktor (klinikte iPad)
- iPad landscape modunda **/dashboard** açık
- **/uyumluluk** ile günlük ISO/KVKK skor kontrolü
- **/hasta-portal/giris?token=...** ile hasta linklerini test
- **/stok** ile ilaç miatları kontrol

### Hasta (kendi telefonu)
- WhatsApp'tan gelen magic link açılır
- `/hasta-portal/giris?token=...&sig=...` → ziyaret listesi
- Recete, USG raporu görür (KVKK-sınırlı)

---

## 5. Bilinen iOS Safari Sınırlamaları

| Sınırlama | Açıklama | Çözüm |
|---|---|---|
| Service Worker storage 7 gün | Site 7 gün kullanılmazsa cache silinir | App standalone modunda günlük açılırsa sorun olmaz |
| Background sync yok | Arka planda sync yapamaz | Cron + push notification ile aşılır |
| Push notif iOS < 16.4 | Yok | iOS 17+ güncel |
| WebRTC mikrofon kullanımı | İzin her sayfa açılışında | "Always Allow" Safari ayarından |
| File upload kamerası | İzin gerekli | İlk kullanımda Allow seç |

---

## 6. Sorun Giderme

### **"Bu site özelliği yok" mesajı**
- Service worker scope `/` olmadığında. Adres çubuğunda `/` ile aç, alt sayfa değil.

### **"Sayfa yüklenemiyor"**
- HTTPS sertifika güvenilir değil. Tailscale Funnel kur veya cert install et.

### **İkon karelı/eski görünüyor**
- Eski cache. Safari → Settings → Clear History → tekrar Add to Home Screen.

### **Yazılar küçük / büyük**
- iOS Dynamic Type. Settings → Display → Text Size küçük/büyük.

### **Alex sesi gelmiyor**
- iOS müzik/video oynatıyor mu? Önce bunu durdur.
- AirPods bağlıyken bazen ses kısık → Volume Up.

### **Form'a tıklayınca zoom yapıyor**
- Input font-size 16px altında. Bu fix'lendi (yk-ios-mobile.css), cache temizle.

### **Notch'tan içerik gözükmüyor**
- viewport-fit=cover meta eksik. Bu fix'lendi.

---

## 7. iPhone'a Özel İpuçları

- **3D Touch / Haptic Touch**: Ana ekran ikonuna basılı tut → "Yeni Hasta", "Randevular", "Dashboard" kısayolları
- **Splash Screen**: iOS otomatik üretir (app icon büyük + arka plan = manifest background_color)
- **App Switcher**: PWA olarak ayrı pencere görünür
- **Picture-in-Picture**: Şu an yok (video oynatma yok)

---

## 8. Test Adımları (Hızlı)

iPhone Safari'de:
1. ✅ `https://...` aç → Giriş sayfası gözükmeli
2. ✅ Login → Dashboard açılmalı
3. ✅ Sağ alt **Paylaş** → Add to Home Screen → "YazKlinik"
4. ✅ Ana ekrandan ikona dokun → tam ekran açılmalı
5. ✅ Status bar mavi (theme-color) görünmeli
6. ✅ Bir input'a dokun → klavye açılırken zoom YAPMAMALI
7. ✅ Alex bar altta görünmeli, dokunmatik çalışmalı
8. ✅ `/status` aç → tüm servisler tablo halinde
9. ✅ `/uyumluluk` aç → grade A-F renkli görünmeli
10. ✅ Telefon yatay çevir → layout bozulmamalı

---

## 9. Performans Notu

iOS'ta WebGL/3D yok ama tüm Session 7 sayfaları **statik HTML + minimal JS** kullanır → çok hızlı. Network tarafında:
- Lokal LAN (Tailscale): ~10-50 ms
- Internet (Tailscale Funnel): ~80-150 ms
- 4G: ~200-400 ms

**Cache**: Service Worker (sw.js) static asset'leri cacheliyor → 2. açılış %80 daha hızlı.

---

## 10. İleri (opsiyonel)

- **VOIP/SIP**: iOS'ta WebRTC ile sesli arama → tarayıcıdan direkt SIP bridge
- **Apple Watch Push**: Tailscale Funnel + Web Push → saat bildirimi
- **Siri Shortcuts**: Manifest shortcut + URL scheme → "Hey Siri, randevuları aç"
- **CallKit benzeri**: Bekleyen iş notification haline gelir

---

**Not**: Tailscale Funnel kurulumu için: `D300_TAILSCALE_FUNNEL_8443_KUR.bat` veya `TAILSCALE_UZAKTAN_ERISIM.md` dosyasına bak.

**Hazırlayan**: Claude AI (2026-05-17)
