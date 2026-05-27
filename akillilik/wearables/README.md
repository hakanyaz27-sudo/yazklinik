# Wearables (Apple Watch / WearOS) Integration - Stub

## Amac

Doktora ve hastaya WatchApp push:
- Doktor saatine: "Yeni randevu talebi", "Acil hasta", "Lab kritik degeri"
- Hasta saatine: "Ilac vakti", "Egzersiz hatirlatma", "Kontrol bugun"

## Teknoloji Secimi

### Apple Watch (watchOS):
- WidgetKit + Live Activities (iOS 16.1+)
- Native Swift app (App Store yayinlanir)
- Push: APNs (Apple Push Notification service)

### WearOS:
- Companion app + Wear Tile
- Push: FCM (Firebase Cloud Messaging)

### Cross-platform Quick Win:
- Web Push (PWA) -> watchOS/WearOS supportu sinirli
- WhatsApp/Telegram bildirimi (gercekten watch'a dusebilir)
- IFTTT / Zapier webhook

## Hizli Baslangic (PWA Push)

PWA service worker zaten `/static/sw.js` icinde push handler var.
Kullanici izin verirse:
```javascript
const reg = await navigator.serviceWorker.register("/static/sw.js");
const sub = await reg.pushManager.subscribe({
  userVisibleOnly: true,
  applicationServerKey: VAPID_PUBLIC_KEY
});
await fetch("/api/push/subscribe", {method: "POST", body: JSON.stringify(sub)});
```

## Production yol haritasi

1. **Faz 1: PWA Push** (1-2 gun) - Bildirim hem mobile hem watch'a (limited)
2. **Faz 2: WatchOS app** (2-4 hafta) - Native Swift + Apple Developer hesap (99 USD/yil)
3. **Faz 3: WearOS** (2-3 hafta) - Kotlin + Play Store

## Push Senaryolari (priority)

| Senaryo | Watch'a dussun mu | Sessizlik |
|---|---|---|
| Acil hasta cagrisi | Evet, vibrate | Hicbir sessiz mode kapatamaz |
| Yeni randevu talebi | Evet | Sessiz mode kapatir |
| Lab kritik degeri | Evet, vibrate | Hicbir |
| Gunluk ozet | Evet (sessiz) | Yeni saat sessiz |
| Birthday hatirlatma | Hayir (sadece phone) | - |

## Status

**STUB - henuz native app yok.** PWA push ile baslayip ihtiyaca gore native gelisir.
