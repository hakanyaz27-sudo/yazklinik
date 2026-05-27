# Yapilmayan Istekleri Kapatma Notu - 2026-05-19

Bu dosya, kullanicinin "yapmadiklarini bul ve yap" istegi icin acilan
ikinci denetim notudur.

## Bu turda bulunan ve kapatilan eksikler

1. Hasta Portal doktor ekraninda iptal/temizlik yoktu.
   - Eklendi: tek link iptal etme.
   - Eklendi: iptal edilmis linki silme.
   - Eklendi: iptal edilmis tum linkleri temizleme.

2. Hasta Portal hasta tarafinda gorsel onizleme/kaydirma yoktu.
   - Eklendi: token korumali resim servis route'u.
   - Eklendi: portal icinde son USG/gorsel kartlari.
   - Eklendi: resme tiklayinca buyuk onizleme, ileri/geri ve ESC kapatma.

3. USG Rapor Taslak ajani aktif hasta yokken bos/hasta listesine dusuyordu.
   - Eklendi: aktif hasta yoksa kendi hasta secim ekrani.
   - Hasta secilince dogrudan `/hasta/<hasta>/usg-rapor-taslak` acilir.

## Kodda mevcut oldugu dogrulanan onceki istekler

1. Ayni tarihli gelisleri tek satir/kartta toplama:
   - `_group_same_day_bulutklinik_visits()` kullaniliyor.
   - `/hasta/<patient>/gelisler` ve takip ekrani ayni tarihleri birlestiriyor.

2. Tetkik listesi dinamik secilebilir/yazdirilabilir:
   - Checkbox secimi, filtreler, A4/A5 print secimi mevcut.

3. BulutKlinik akilli siniflandirma:
   - `yazklinik_bk_voluson_mirror.py` icinde recete/hikaye/tani/plan
     puanlama ve yanlis recete aynalamayi engelleme mevcut.

4. Ajan modulleri:
   - `YAZKLINIK_AGENT_FOCUS_AUDIT.py` sonucu: 42/42 modul yuklu,
     42/42 focus OK, 19/19 registry guardrail OK.

## Kalan canliya alma notu

Kod dosyalari hazir ve compile geciyor. Ancak mevcut web sureci Windows
tarafindan korumali/eski `pythonw.exe` PID olarak 5052/5443 portlarini tutuyor.
Bu nedenle yeni web degisiklikleri canliya tamamen gecmesi icin
`D500_ADMIN_WEB_RESTART.bat` yonetici onayi ile calismali.

## Bilerek yapilmayan

Google Ads otomatik tiklama botu click-fraud riski nedeniyle yapilmadi.
Guvenli alternatif savunma/invalid traffic raporu tarafidir.
