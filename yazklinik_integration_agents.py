"""YazKlinik external integration agent registry.

This module is intentionally stdlib-only and side-effect free.  It describes
which external systems can be connected safely, which direction the data can
move, and which parts must wait for an official API/contract or an explicit
doctor approval step.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime


AGENT_VERSION = "2026.05.16-integration-agents-ig-ceviri-konsult"


INTEGRATION_AGENTS = [
    {
        "id": "bulutklinik",
        "name": "BulutKlinik Aktarim Ajani",
        "short": "Hasta, randevu ve laboratuvar aktarimi icin resmi API connector.",
        "status": "ready_with_credentials",
        "risk": "medium",
        "directions": ["YazKlinik -> BulutKlinik", "BulutKlinik -> YazKlinik"],
        "panel_route": "/bulutklinik",
        "api_endpoints": [
            "POST /api/bulutklinik/credentials",
            "POST /api/bulutklinik/connect",
            "GET  /api/bulutklinik/branches",
            "GET  /api/bulutklinik/lab/<barcode>",
            "POST /api/bulutklinik/randevu/preview",
            "POST /api/bulutklinik/randevu/olustur",
        ],
        "safe_methods": [
            "Resmi BulutKlinik OAuth (apiClientId + apiSecretKey + kullanici)",
            "Token bellek icinde, refresh ile yenilenir",
            "Tum istekler web_audit_log'a 'bulutklinik:*' aksiyonuyla yazilir",
            "Tek tek hasta/randevu icin onay kuyrugu",
            "CSV disari aktarim ve doktor onayli ice aktarim",
        ],
        "blocked_methods": [
            "Kullanici sifresini saklayip arka planda panel gezme",
            "Onaysiz toplu hasta verisi gonderme",
        ],
        "doctor_actions": [
            "BulutKlinik panel > Ayarlar > API erisim bilgileri sayfasindan 4 alan alinir",
            "/bulutklinik sayfasinda apiClientId/secret/user/password girilir + Baglanti Testi",
            "Brans listesi/lab barkod testleriyle dogrulama",
            "Aktarim onay ekranindan tek tek veya toplu onay verilir",
        ],
    },
    {
        "id": "enabiz",
        "name": "e-Nabiz Belge Okuma Ajani",
        "short": "Hasta paylasimli PDF/rapor/tahlilleri OCR + YZ ile yapilandirir, doktor onayiyla hasta dosyasina yazar.",
        "status": "ready_with_patient_consent",
        "risk": "high",
        "directions": ["e-Nabiz belge -> YazKlinik (hasta paylasimi)"],
        "panel_route": "/enabiz",
        "api_endpoints": [
            "POST /api/enabiz/upload",
            "POST /api/enabiz/onayla",
            "GET  /api/enabiz/gecmis",
        ],
        "safe_methods": [
            "Hasta e-Nabiz mobil uygulamasindan PDF indirir, doktora getirir",
            "PyMuPDF metin cikarir; pdf_patient_extract demografi/tahlil/USG aday yapilandirir",
            "Hasta eslestirme (TC/telefon/ad-soyad puani) en yakin 5 hastayi onerir",
            "Doktor onay sonrasi _patient_data_suggest_demographics gate'inden gecer",
            "Tum aktarimlar web_audit_log'a 'enabiz:*' aksiyonuyla yazilir",
        ],
        "blocked_methods": [
            "e-Nabiz/e-Devlet sifresiyle otomatik giris (KVKK + SBYS yasak)",
            "Sahis verisi tarama veya arka plan toplu cekim",
            "Resmi REST API yok; SBYS XML servisleri sadece kuruma kayitli SBYS yazilimlari icin",
        ],
        "doctor_actions": [
            "Hasta e-Nabiz uygulamasindan PDF/rapor paylasir",
            "/enabiz sayfasinda PDF surukle-birak yuklenir",
            "Imza tespiti + aday hasta listesi + alan secimi",
            "Doktor onay sonrasi hasta dosyasina yazilir; cakisma onay kuyruguna duser",
        ],
        "official_paths_outside_scope": [
            "SBYS XML paket gonderimi (KTS kayitli sigorta/hastane yazilimlari icin sys.sagliknet.saglik.gov.tr/SYS/SYSWS.svc)",
            "Hekim Sorgu Hizmeti (enabiz.gov.tr/Provider) - manuel web portal, API degil",
        ],
    },
    {
        "id": "doktortakvimi",
        "name": "DoktorTakvimi Randevu Ajani",
        "short": "Randevulari YazKlinik takvimiyle eslestirir.",
        "status": "official_export_or_api_required",
        "risk": "medium",
        "directions": ["DoktorTakvimi -> YazKlinik", "YazKlinik -> DoktorTakvimi"],
        "safe_methods": [
            "Resmi API/partner erisimi varsa iki yonlu senkron",
            "CSV/ICS/takvim disari aktarimi varsa ice aktarma",
            "YazKlinik randevusunu DoktorTakvimi icin onay kuyruguna alma",
        ],
        "blocked_methods": [
            "Tarayici sifresiyle otomatik panel kullanma",
            "Kullanicinin gormedigi arka plan randevu degisikligi",
        ],
        "doctor_actions": [
            "Randevu kaynagi baglanir",
            "Ayni telefon/ad-soyad ile eslestirme yapilir",
            "Cakisma varsa doktor onaylar",
        ],
    },
    {
        "id": "randevu_sohbet",
        "name": "Randevu ve Sohbet Merkezi Ajani",
        "short": "WhatsApp/telefon/web taleplerini tek kuyrukta toplar.",
        "status": "ready_internal",
        "risk": "low",
        "directions": ["Dis talep -> YazKlinik", "YazKlinik -> hatirlatma"],
        "safe_methods": [
            "Telefon/WhatsApp metnini randevu adayina cevirme",
            "Cakisan saatleri otomatik yakalama",
            "Doktor/sekreter onayindan sonra takvime yazma",
        ],
        "blocked_methods": [
            "Onaysiz randevu degistirme",
            "Hastaya doktor onayi olmadan klinik karar mesaji gonderme",
        ],
        "doctor_actions": [
            "Ajan onerir",
            "Sekreter/doktor onaylar",
            "Hasta bilgilendirme mesaji hazirlanir",
        ],
    },
    {
        "id": "kvkk_denetimevi",
        "name": "KVKK ve Denetim Ajani",
        "short": "Her dis veri hareketini kayda alir ve onay izi tutar.",
        "status": "recommended_internal",
        "risk": "low",
        "directions": ["YazKlinik ic kontrol"],
        "safe_methods": [
            "Kim, ne zaman, hangi hastayi aktardi kaydi",
            "Onay metni ve veri yonu kaydi",
            "Geri alma / aktarim raporu",
        ],
        "blocked_methods": [
            "Sessiz arka plan aktarimi",
            "Log tutmadan hassas veri paylasimi",
        ],
        "doctor_actions": [
            "Onay metinleri belirlenir",
            "Aktarimlar loglanir",
            "Aylik denetim raporu uretilir",
        ],
    },
    {
        "id": "eslestirme",
        "name": "Hasta Eslestirme ve Tekillestirme Ajani",
        "short": "Dis kaynaklardan gelen hastayi YazKlinik hasta kartiyla eslestirir.",
        "status": "recommended_internal",
        "risk": "low",
        "directions": ["Dis veri -> YazKlinik"],
        "safe_methods": [
            "Telefon, protokol, ad-soyad ve dogum tarihiyle puanlama",
            "Supheli eslesmeleri doktor onayina birakma",
            "Ayni hastayi iki kere acmayi engelleme",
        ],
        "blocked_methods": [
            "Dusuk guvenle otomatik birlestirme",
            "Kimlik numarasini acik ekranda gereksiz gosterme",
        ],
        "doctor_actions": [
            "Ajan eslesme skoru verir",
            "Kullanici onaylar",
            "Kayitlar birlestirilir veya ayri tutulur",
        ],
    },
    {
        "id": "telesekreter",
        "name": "YZ Telesekreter Ajani",
        "short": "Kacirilan/kapali saatte gelen aramalari triyaj eder; aciliyet ve niyet siniflandirir.",
        "status": "ready_internal",
        "risk": "medium",
        "directions": ["Telefon/sip2sip -> YazKlinik onay kuyrugu"],
        "module": "yazklinik_telesekreter_agent",
        "entry_function": "parse_call",
        "safe_methods": [
            "STT cikti ve caller-ID alir; klinik karar vermez",
            "Niyet: yeni randevu / iptal / acil / bilgi / spam",
            "Aciliyet skoru sadece siralama icindir",
            "Sonuc onay kuyruguna duser, doktor/sekreter karar verir",
        ],
        "blocked_methods": [
            "Hastaya klinik bilgi veya tani vermek",
            "Randevuyu otomatik kesinlestirmek (sesli_onay ajani isi)",
            "Caller listesini disariya gondermek",
        ],
        "doctor_actions": [
            "Onay kuyrugundan tek tek cagri inceler",
            "Uygun bulursa randevu / arama / SMS aksiyonu baslatir",
            "Spam'ler reddedilir, kayit kalir",
        ],
    },
    {
        "id": "sesli_onay",
        "name": "Sesli Randevu Evet Onayi Ajani",
        "short": "Hasta sesli 'evet/hayir/ertele' yanitini siniflandirir, otomatik onay icin guven esigi uygular.",
        "status": "ready_internal",
        "risk": "medium",
        "directions": ["Telefon STT yaniti -> randevu state degisikligi"],
        "module": "yazklinik_sesli_onay_agent",
        "entry_function": "decide",
        "safe_methods": [
            "Evet/hayir/ertele/belirsiz/yanit yok siniflandirir",
            "can_auto_apply() yuksek guvende sadece confirm/cancel uygular",
            "Belirsiz/erteleme her zaman insan review",
        ],
        "blocked_methods": [
            "Tereddutlu yanitta otomatik karar",
            "Insan review olmadan randevu silme",
        ],
        "doctor_actions": [
            "Sekreter unclear durumlarini dinler",
            "Auto-onay esigi ayarlanabilir",
        ],
    },
    {
        "id": "usg_rapor",
        "name": "USG Rapor Taslak Ajani",
        "short": "BPD/HC/AC/FL olcumlerinden Hadlock EFW + standart sablon rapor TASLAGI uretir.",
        "status": "ready_internal",
        "risk": "high",
        "directions": ["Voluson olcum -> rapor taslagi"],
        "module": "yazklinik_usg_rapor_agent",
        "entry_function": "build_draft",
        "safe_methods": [
            "Sablonlanmis taslak metin",
            "Hadlock IV ile EFW kestirimi (rapor amacli)",
            "+/- 2SD disindaki olcumlere DIKKAT etiketi",
        ],
        "blocked_methods": [
            "Klinik tani veya 'normal/anormal' yargisi",
            "Otomatik hasta dosyasina yazma",
            "NAS USG goruntusunu silme/tasima",
        ],
        "doctor_actions": [
            "Taslagi ekrandan duzeltir",
            "Imzalayip hasta dosyasina yazar",
        ],
    },
    {
        "id": "geri_cagirma",
        "name": "Hasta Geri Cagirma Ajani",
        "short": "Kontrol/asi/postop hatirlatma kuyrugu olusturur; aylik mesaj limiti ve KVKK kontrolu uygular.",
        "status": "ready_internal",
        "risk": "medium",
        "directions": ["YazKlinik hasta listesi -> WhatsApp/SMS kuyrugu"],
        "module": "yazklinik_geri_cagirma_agent",
        "entry_function": "bulk_schedule",
        "safe_methods": [
            "Sadece sablonlanmis hatirlatma metni (klinik bilgi YOK)",
            "Aylik mesaj limiti (varsayilan 2)",
            "Iletisim KVKK rizasi olmayan hastalari atlar",
        ],
        "blocked_methods": [
            "Tani/sonuc/recete bilgisini WhatsApp ile gondermek",
            "Blok listesindeki numaraya mesaj",
        ],
        "doctor_actions": [
            "Sablon paketleri tanimlar",
            "Toplu hatirlatma kuyrugunu onaylar",
        ],
    },
    {
        "id": "bk_sync_bekci",
        "name": "BulutKlinik Sync Bekci Ajani",
        "short": "OAuth/cookie/CDP saglik kontrolu; kopuk veya stale durumda doktora uyari verir.",
        "status": "ready_internal",
        "risk": "low",
        "directions": ["YazKlinik ic gozlem"],
        "module": "yazklinik_bk_sync_bekci_agent",
        "entry_function": "check_status",
        "safe_methods": [
            "ok / stale / expired / unreachable / unknown durumlari",
            "Onerilen aksiyon metni (token yenile, cookie tazele, CDP baglan)",
            "Esik asarsa doktor sayfa et",
        ],
        "blocked_methods": [
            "Otomatik sifre yenileme",
            "Token saklamak (web layer state isi)",
        ],
        "doctor_actions": [
            "/bulutklinik panelinde uyari banneri gorur",
            "Onerilen aksiyonu uygular",
        ],
    },
    {
        "id": "nas_yedek_izleyici",
        "name": "NAS Yedek Izleyici Ajani",
        "short": "Asustor yedek dosyalarini periyodik kontrol eder; boyut/zaman/disk doluluk uyarilarini cikarir.",
        "status": "ready_internal",
        "risk": "low",
        "directions": ["NAS read-only -> rapor"],
        "module": "yazklinik_nas_yedek_izleyici_agent",
        "entry_function": "check_health",
        "safe_methods": [
            "Sadece read; stat ve disk_usage cagrilari",
            "Son yedek zaman, sayisi, medyan boyut sapmasi",
            "Disk doluluk %85 warn / %95 critical",
        ],
        "blocked_methods": [
            "Hicbir dosya silme/tasima",
            "Hasta verisini ag uzerinden tasima",
            "Otomatik yedek alma",
        ],
        "doctor_actions": [
            "Critical uyarida elle yedek calistirir",
            "Disk dolma uyarisinda arsivleme planlar",
        ],
    },
    {
        "id": "recete_hazirlayici",
        "name": "Recete Hazirlayici Ajani",
        "short": "Hasta gecmisi + doktor sablonlarindan recete TASLAGI; alerji/etkilesim uyarilar.",
        "status": "ready_internal",
        "risk": "high",
        "directions": ["Hasta dosyasi -> recete taslak"],
        "module": "yazklinik_recete_hazirlayici_agent",
        "entry_function": "build_draft",
        "safe_methods": [
            "Son 90 gun ilac deseninden oneri",
            "Alerji ile eslesen ilaclari otomatik eler",
            "Etkilesim ipuclarini DIKKAT etiketiyle gosterir",
        ],
        "blocked_methods": [
            "Otomatik imza/e-Recete gonderimi",
            "Tani veya doz onerisi",
            "Alerji listesi olmayan hasta icin oneri",
        ],
        "doctor_actions": [
            "Taslagi inceler, dozaj/sure yazar, imzalar",
        ],
    },
    {
        "id": "gunluk_ozet",
        "name": "Gunluk Klinik Ozet Ajani",
        "short": "Gun sonunda hasta trafigi, ciro, bekleyen onay ve yarinki program ozetini hazirlar.",
        "status": "ready_internal",
        "risk": "low",
        "directions": ["YazKlinik ic veri -> WhatsApp/e-posta metni"],
        "module": "yazklinik_gunluk_ozet_agent",
        "entry_function": "build_summary",
        "safe_methods": [
            "Sadece sayilar ve insiyaller (PII yok)",
            "Kisa (WhatsApp <320 char) ve uzun metin",
            "Dunle karsilastirma yuzdesi",
        ],
        "blocked_methods": [
            "Hasta tam adi veya tani metni paylasimi",
            "SGK fatura beyani",
        ],
        "doctor_actions": [
            "Gunluk ozeti inceler, WhatsApp'a iletir",
        ],
    },
    {
        "id": "mojibake_bekci",
        "name": "Mojibake Bekci Ajani (DETECT-ONLY)",
        "short": "Cift encode kaynakli karakter bozulmalarini tespit eder; OTOMATIK DUZELTME YAPMAZ.",
        "status": "ready_internal",
        "risk": "low",
        "directions": ["Repo read-only -> rapor"],
        "module": "yazklinik_mojibake_bekci_agent",
        "entry_function": "scan_tree",
        "safe_methods": [
            "Klasoru gezer, UTF-8 okur, mojibake desen sayar",
            "Yogunluk esikleriyle warn/critical isaretler",
            "Dosya icerigine asla yazmaz",
        ],
        "blocked_methods": [
            "Otomatik decode/recode",
            "Toplu dosya yeniden yazma",
            "Pre-commit hook'u kendi kendine kurma",
        ],
        "doctor_actions": [
            "Rapora bakar, gerekirse el ile duzeltir veya Codex'e tasitir",
        ],
    },
    {
        "id": "pr_reviewer",
        "name": "PR Reviewer Ajani",
        "short": "Diff'i sablon kurallarina karsi tarar (v68 dokunmasi, hasta DELETE, NAS unlink, mojibake, mass format).",
        "status": "ready_internal",
        "risk": "low",
        "directions": ["Git diff metni -> rapor"],
        "module": "yazklinik_pr_reviewer_agent",
        "entry_function": "review_diff",
        "safe_methods": [
            "Diff metnini parse eder",
            "Blocker / warn / info seviyeleri",
            "Yorum birakmaz, sadece kullaniciya rapor verir",
        ],
        "blocked_methods": [
            "PR'i otomatik approve/reject",
            "GitHub'a yorum push",
            "Yerel branch'e degisiklik commit",
        ],
        "doctor_actions": [
            "Rapora bakar, blocker varsa PR'i reddeder",
            "Warn'lari Codex'e tasitir",
        ],
    },
    {
        "id": "instagram",
        "name": "Instagram Hazirlik Ajani",
        "short": "USG arsivinden Instagram icin guzel goruntuler secer, anonimlestirir, iyilestirir; draft klasorune kaydeder. ASLA otomatik post atmaz.",
        "status": "ready_internal",
        "risk": "high",
        "directions": ["NAS USG arsivi (read) -> instagram_drafts (yaz)"],
        "module": "yazklinik_instagram_agent",
        "entry_function": "scan_archive",
        "panel_route": "/instagram-hazirla",
        "api_endpoints": [
            "POST /api/agents/instagram/scan",
            "GET  /api/agents/instagram/thumbnail",
            "POST /api/agents/instagram/enhance",
            "POST /api/agents/instagram/caption",
            "GET  /api/agents/instagram/draft-download",
        ],
        "safe_methods": [
            "Arsivi sadece OKUR; orijinal dosyalar degistirilmez/silinmez",
            "Ust strip (hasta bilgi seridi) VARSAYILAN OLARAK kirpilir",
            "Iyilestirme PIL ile yapilir, sonuc instagram_drafts/ klasorune yazilir",
            "Caption + hashtag yalniz sablon kutuphanesinden uretilir",
            "Path-traversal koruma: izinli koklerin disindaki dosyalar reddedilir",
            "KVKK kontrol listesi (7 madde) doktor onayina sunulur",
        ],
        "blocked_methods": [
            "Instagram API ile otomatik post atma",
            "Orijinal NAS dosyasini degistirme / silme",
            "Hasta yazili onayi olmadan 'ready_to_post' isaretleme",
            "Goruntu disinda hasta verisi (PII) drafta yazma",
            "Caption icine hasta adi / vakaya ozgu bilgi koyma",
        ],
        "doctor_actions": [
            "/instagram-hazirla sayfasinda klasor verir, tarar",
            "Aday gridinden begendiklerini secer",
            "Crop / netlik / kontrast slider'lariyla ince ayar yapar",
            "Drafta kaydeder; sonra ChatGPT veya Instagram Editor ile son rotusu yapar",
            "Caption sablonu uretir, hashtag setini secer, manuel rafine eder",
            "KVKK kontrol listesini madde madde isaretler",
            "Instagram'a manuel olarak yukler (ajan otomatik yapmaz)",
        ],
    },
    {
        "id": "konsult",
        "name": "YZ Konsultasyon Ajani (OB-GYN, 5-step)",
        "short": "Vaka -> kirmizi alarm + ayirici tani + tetkik + tedavi + takip. Multi-step LLM zinciri (qwen2.5:32b yerel). Klinik karar destek.",
        "status": "ready_internal",
        "risk": "high",
        "directions": ["Doktorun yazdigi vaka -> yapilandirilmis konsultasyon raporu"],
        "module": "yazklinik_konsult_agent",
        "entry_function": "full_consultation",
        "panel_route": "/yz-konsultasyon",
        "api_endpoints": [
            "GET  /api/agents/konsult/health",
            "POST /api/agents/konsult/extract  (sadece vaka yapilandir)",
            "POST /api/agents/konsult/full     (5 adimli tam zincir)",
        ],
        "safe_methods": [
            "Multi-step prompt: extract -> ddx -> workup -> treatment -> followup",
            "Her adim ayri JSON-only LLM cagrisi (parse failsafe ile)",
            "OB-GYN persona prompt + ACOG/RCOG/TJOD referansi",
            "Gebelik FDA kategorisi (A/B/C/D/X) zorunlu",
            "Kirmizi alarm ilk gosterilir",
            "Sonuc markdown export, panoya, Alex'e gonder",
            "Yerel Ollama varsayilan (hasta verisi PC'den cikmaz)",
        ],
        "blocked_methods": [
            "Otomatik recete yazma (sadece taslak / oneri)",
            "Hasta dosyasina otomatik kayit",
            "X-kategori ilac onerme (gebede)",
            "Klinik direktif tonu (her cikti 'oneri' olarak isaretli)",
        ],
        "doctor_actions": [
            "/yz-konsultasyon sayfasinda vaka tarifini yazar",
            "5 adimli rapor uretilir: kirmizi alarm + DDx + tetkik + tedavi + takip",
            "Her oneri 'doktor onayi bekler' etiketli",
            "Markdown indirir / kopyalar / Alex'e gonderir",
            "Hasta dosyasina manuel ekler (otomatik degil)",
        ],
    },
    {
        "id": "ceviri",
        "name": "Tibbi Ceviri Ajani (PubMed + LLM)",
        "short": "Ingilizce PubMed makalesi ya da serbest metin -> Turkce ceviri + ozet. Ollama yerel (qwen2.5:32b), OpenAI fallback, ChatGPT prompt cikartma.",
        "status": "ready_internal",
        "risk": "low",
        "directions": ["PubMed E-utilities (read) -> LLM (yerel/yabanci) -> Turkce metin"],
        "module": "yazklinik_ceviri_agent",
        "entry_function": "translate_pubmed_article",
        "panel_route": "/ceviri-merkezi",
        "api_endpoints": [
            "GET  /api/agents/ceviri/health",
            "POST /api/agents/ceviri/pubmed-search",
            "POST /api/agents/ceviri/pubmed-fetch",
            "POST /api/agents/ceviri/translate",
            "POST /api/agents/ceviri/summarize",
            "POST /api/agents/ceviri/translate-pubmed",
            "POST /api/agents/ceviri/prompt",
        ],
        "safe_methods": [
            "Once Ollama yerel (qwen2.5:32b - hasta verisi PC'den cikmaz)",
            "OpenAI sadece kullanici acik tercih ederse",
            "Sablonlu medikal Turkce ceviri promptu",
            "OB-GYN agirlikli glossary (60+ terim) prompt'a otomatik eklenir",
            "PubMed E-utilities ucretsiz (API key gerekmez)",
            "Sonuc markdown export, panoya kopyala, Alex'e gonder",
        ],
        "blocked_methods": [
            "Hasta verisi (isim/TC/protokol) yabanci LLM'e gonderme",
            "Klinik tani veya tedavi onerisi yazma",
            "PubMed API'sine hasta kimligi koyma",
        ],
        "doctor_actions": [
            "/ceviri-merkezi'nde sorgu yazip PubMed'i arar",
            "Begendigi makaleyi tiklar -> otomatik ceviri + ozet",
            "VEYA serbest metin yapistirip ceviri/ozet alir",
            "Yabanci LLM kullanmak istemiyorsa 'Sadece prompt' modu",
            "Sonucu markdown indirir, kopyalar veya Alex'e gonderir",
        ],
    },
]


CONNECTOR_POLICY = {
    "principles": [
        "Hasta verisi dis sisteme sadece acik doktor/onay adimiyla gider.",
        "Resmi API yoksa varsayilan yol CSV/ICS/PDF ice aktarimidir.",
        "Sifre saklayip web panelini otomatik gezme varsayilan olarak kapali tutulur.",
        "Her aktarim denetim kaydina yazilmalidir.",
        "YZ ciktilari klinik karar degil, doktor onayi bekleyen adaydir.",
    ],
    "recommended_build_order": [
        "1. Ajan merkezi ve connector durum ekrani",
        "2. CSV/ICS/PDF ice aktarma ve hasta eslestirme",
        "3. BulutKlinik resmi API anahtariyla iki yonlu connector",
        "4. DoktorTakvimi resmi export/API varsa randevu senkronu",
        "5. KVKK denetim ve aktarim raporlari",
    ],
}


def get_integration_agents() -> dict:
    """Return a serializable integration agent manifest."""
    return {
        "ok": True,
        "version": AGENT_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "agents": deepcopy(INTEGRATION_AGENTS),
        "policy": deepcopy(CONNECTOR_POLICY),
    }


def agent_status_counts() -> dict:
    counts = {}
    for agent in INTEGRATION_AGENTS:
        status = str(agent.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts
