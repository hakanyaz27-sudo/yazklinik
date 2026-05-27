# YazKlinik D700 - Figma UI Handoff

Bu not Figma icinde D700 ekranlarini tasarima cevirirken kullanilacak kisa rehberdir.

## Ana ekranlar

1. Giris: `/giris`
2. Dashboard: `/`
3. Hasta listesi: `/hastalar`
4. Hasta dosyasi: `/hasta/<key>`
5. Akilli Dialog / Alex: `/akilli-dialog`
6. Ses ve Alex: `/ses-ve-alex`
7. Sistem ayarlari: `/sistem-ayarlari`
8. Ajanlar: `/ajanlar`
9. Hizmet ajanlari: `/hizmet-ajanlari`
10. Entegrasyonlar: `/entegrasyonlar`

## Tasarim kurallari

1. Klinik hiz oncelikli: hasta bulma, dosya acma, rapor/recete cikti butonlari tek bakista gorunmeli.
2. Kontrast yuksek olmali: kart metinleri ve menu butonlari karanlik/aÃ§ik temada okunmali.
3. Alex gorunur ama sakin olmali: varsayilan mod gorunur/sessiz.
4. Hasta veri aksiyonlari ayrilmali: gor, yazdir, arsivle, sil gibi isler ayni renkte olmamali.
5. Mobilde en onemli 3 aksiyon ustte kalmali: hasta ara, yeni hasta, Alex.

## Figma icin renk tokenlari

```text
Primary: #0f766e
Accent: #d97706
Danger: #b91c1c
Surface: #f8fafc
Ink: #172033
Muted: #64748b
```

## Teslim sekli

Figma'da her ekran icin 1440px desktop ve 390px mobile frame olustur.
Buton/kart komponentlerini tekrar kullanilabilir component olarak ayir.

