# YazKlinik D700 - WAVE / Axe Erisilebilirlik Kontrolu

Bu dosya bugun soz verilen WAVE/Axe tarafinin proje icindeki calisma notudur.

## Komut satiri Axe kontrolu

```powershell
Set-Location "D:\YazKlinik_Final_D500"
npm run axe
```

Varsayilan hedefler:

- `https://127.0.0.1:5443/giris`
- `https://127.0.0.1:5443/status`

Farkli adres icin:

```powershell
$env:YK_BASE_URL="https://192.168.1.50:5443"
npm run axe
```

## WAVE manuel kontrolu

WAVE bir tarayici/online erisilebilirlik aracidir. En pratik akÄ±ÅŸ:

1. Chrome veya Edge WAVE eklentisini ac.
2. `https://127.0.0.1:5443/giris` sayfasini kontrol et.
3. Sonra login olup `/hastalar`, `/akilli-dialog`, `/sistem-ayarlari` ekranlarini kontrol et.
4. Kirmizi hata varsa once label/kontrast/alt text duzelt.

## Hedef kural

Yeni UI degisikligi sonrasi en az:

1. `npm run pw`
2. `npm run axe`
3. `npm run lighthouse_login`

calismali.

