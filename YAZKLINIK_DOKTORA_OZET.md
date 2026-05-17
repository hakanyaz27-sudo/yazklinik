# YazKlinik - Op. Dr. Hakan YAZ Klinik Yonetim Sistemi

> Bir cumle: **Kendi PC'nde calisan, butun hasta isini tek pencereden yapan, KVKK uyumlu, yapay zeka destekli klinik yazilim.**

---

## Ne Ise Yariyor (kisaca)

### Hasta Dosyasi Yonetimi
- Hasta kaydi, anamnez, ozgecmis, soygecmis, alerji, ilac listesi
- Randevu takvimi (gunluk/haftalik/aylik)
- Recete yazma + e-recete PDF
- USG PDF (Voluson) otomatik import - kilo/boy/tansiyon/LMP/gebelik haftasi visit'e direkt isleniyor
- BulutKlinik ile otomatik senkron (bekci ajan kontrol ediyor)
- NAS yedekleme + restic sifreli backup

### Yapay Zeka Destegi (Lokal - hicbir veri disariya cikmaz)
- **YZ Konsultasyon**: Vaka anlatirsin, 5 adimda anamnez ozeti + ayirici tani + tetkik planlama + tedavi onerisi + takip plani uretir (meditron:70b modeli)
- **USG Goruntu Analizi**: USG fotografi yukle -> AI modality/view/biometri/IG potansiyeli analiz eder (llama3.2-vision)
- **SOAP Genisletici**: 2 satir not yaz -> tam SOAP formati (Subjective/Objective/Assessment/Plan) uretir
- **ICD-10 Kod Oneren**: Tani metnini yaz -> en uygun 5 ICD-10 kodu siralanir
- **PubMed Cevirici**: Ingilizce makaleyi otomatik Turkceye cevirir + ozet uretir + RAG'a kayit
- **Alex Sesli Asistan**: Sesle konus, dosya ac, randevu sor, kayit acindan

### Klinik Karar Destek (kanit bazli)
- **DDI - Ilac Etkilesim Kontrolu**: Recete yazinca otomatik kontrol (warfarin+aspirin, methotrexate+amoxicillin vs)
- **Gebelik FDA Kategori X/D Uyarisi**: Gebede kontrendike ilac yazarsan kirmizi alarm
- **Preeklampsi Risk Skoru**: SBP/DBP/proteinuri/sintomi -> risk seviyesi
- **HELLP Mississippi Siniflandirma**: Hemoliz + AST + trombosit -> evre I/II/III
- **Bishop Skoru**: Servikal olcum -> dogum indikasyonu hazirlik
- **VTE Padua Skoru**: Yatan hastada tromboz riski
- **Gebelik Takvimi**: LMP gir -> NT taramasi (11-14), morfoloji (18-22), GDM (24-28), GBS (35-37), dogum cantasi (37) tarihleri otomatik
- **Smear/HPV Takip (ASCCP 2019)**: ASCUS+HPV+ -> kolposkopi tarihi otomatik onerilir
- **PHQ-9 Postpartum Depresyon Taramasi**: 9 soru -> skor + intihar riski uyarisi

### Otomasyonlar (siz uyurken)
- **Gunluk hasta ozeti** (her aksam): kac hasta, hangi tani, hangi ilac
- **Anti-burnout dashboard**: gun icinde 4 saat mola yapmadiysan uyari ("10 dk durun, su icin")
- **Stok takip**: ilac biterken / miat dolarken WhatsApp uyari
- **Memnuniyet anketi** (her sabah 09:00): dun gelen hastalara WhatsApp 5-yildiz sorma
- **Dogum gunu tebrikleri** (her sabah): bugun dogan hastalara kisa mesaj
- **PubMed otomatik tarama**: 8 sorgu (preeklampsi, PCOS, FGR vs) gunluk yeni makale Turkce ozetleri
- **NAS yedek bekci**: yedek 24s eski ise alarm
- **Mojibake bekci**: Turkce karakter bozulmasi tarar (TESPIT only - duzeltmez)
- **Backup verify**: restic + SQLite integrity her gece kontrol

### Hasta Iletisim
- **Hatira USG**: USG'den guzel kareyi otomatik kirpip, watermark + tatli sablonla anneye WhatsApp (consent ile)
- **Instagram Hazirlik**: USG fotosunu KVKK-anonim Insta postu olarak hazirlar (header bilgileri silinir)
- **Hasta Self-Service Portal**: hasta telefonuna magic link yollar -> ziyaretlerini, recetelerini, raporlarini gorur
- **WhatsApp Bot (n8n)**: hastadan gelen "randevu" mesajini parse eder, randevu sistemine baglar
- **Geri Cagirma Ajani**: lab sonucu cikan / kontrolu gelmeyen hastalari listeler + WhatsApp gonderir

### Guvenlik (KVKK + ISO 27001)
- **Uyumluluk Panosu** (`/uyumluluk`): A+ ile F arasi anlik skor + eksikler listesi
- **2FA TOTP**: Google Authenticator ile 6 hane dogrulama
- **Hasta Magic-Link**: 24s sureli tek kullanim link, sifre yok
- **Audit Log**: kim ne zaman ne yapti hepsi kayit
- **Hasta Riza (KVKK)**: tablo + UI - hasta rizasi olmadan WhatsApp/Insta gonderim BLOK
- **Sifreleme**: HTTPS (TLS) + Vaultwarden sifre yoneticisi (Docker)
- **Uzaktan erisim**: Tailscale Funnel ile sifreli, sadece sizin ag

### Yan Yardimci Programlar (kurulu)
- **Vaultwarden**: sifre yoneticisi (kendi serverinde, Bitwarden ile uyumlu)
- **Uptime Kuma**: serverin canli mi takip dashboard
- **n8n**: WhatsApp + e-posta + takvim otomatik akislari
- **Open WebUI**: ChatGPT benzeri arayuz, lokal Ollama'ya baglaniyor
- **OHIF Viewer**: DICOM goruntuleyici (USG/MR/CT browser'da)
- **Stirling-PDF**: PDF birlestir/bol/imzala/sifrele
- **3D Slicer**: medikal goruntu segmentasyon
- **Tesseract OCR**: PDF/foto'dan metin cikarma
- **Zotero**: makale referans yoneticisi

### Veri Tabani / Arama
- **PostgreSQL 16**: ileri sorgu icin (yedek SQLite ana)
- **Redis 7**: hizli cache + kuyruk
- **MeiliSearch v1.13**: 15.936 hasta+ziyaret+recete kaydinda saniye altinda typo-tolerant arama
- **ChromaDB + BGE-M3 RAG**: tum belgelerinizden semantic arama ("preeklampside fluniraridine ne yapilir?")

### Telefon / Cagri / Randevu
- **SIP Bridge**: gelen cagrinin sesi STT'den gecip telesekreter triyaji ile siralanir
- **Sesli Onay**: ses ile "evet randevuyu onayliyorum" -> randevu state'i degisir
- **Telesekreter Triaj**: cagri kayitlari acil/randevu/diger seklinde otomatik etiketler

### Doktor Kendi Verimliligi
- **Anti-Burnout**: hasta sayisi, en uzun mola olmadan calisma, haftalik trend; "ACIL: bu hafta hasta sayini azalt" uyarisi
- **Voice Command**: "BPD 85" / "tansiyon 158/102" / "kilo 72.5" sesli komut -> direkt formuna girer
- **Multi-Agent Orchestrator**: "tam ziyaret" tek komut -> konsult + ICD-10 + DDI + SOAP zincirleme uretir

---

## Ozetin Ozeti (5 madde)

1. **Hicbir veri disari cikmaz** - tum yapay zeka lokal (kendi RTX 5090 PC'nde calisiyor, ChatGPT'ye gondermez)
2. **Hasta bilgisinin sifirdan dogru olmasi** - PDF/yazma/sesli her yoldan tek yere yaziliyor, mojibake bekcisi var
3. **Klinik karar destek** - ilac etkilesimi, gebelik kategorisi, risk skorlari, ASCCP smear takibi, gebelik takvimi otomatik
4. **Otomasyon** - memnuniyet anketi, dogum gunu, yedek, stok, PubMed taramasi hep otomatik
5. **KVKK + ISO 27001** - audit log, hasta rizasi, 2FA, uzaktan erisimde sifre, anlik uyumluluk skoru

---

## Teknik Detay (doktor isterse)

- **Stack**: Python + Flask + SQLite (ana) + Docker (yardimci servisler)
- **PC**: RTX 5090 (yerel AI icin)
- **AI Modelleri**: Ollama (meditron:70b, qwen2.5:32b, llama3.2-vision:11b, bge-m3, yaz:latest)
- **Adres**: https://127.0.0.1:5443 (lokal) + Tailscale ile uzaktan
- **Klinik adi**: D300 (4. nesil, surekli iyilesen)
- **Tek tikla baslatma**: D300_BASLAT.bat
- **Yedek**: gunluk restic sifreli + NAS Asustor

---

*Hazirlayan: Claude AI (Op. Dr. Hakan YAZ icin gelistirildi - Mayis 2026)*
