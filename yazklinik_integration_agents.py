"""YazKlinik external integration agent registry.

This module is intentionally stdlib-only and side-effect free.  It describes
which external systems can be connected safely, which direction the data can
move, and which parts must wait for an official API/contract or an explicit
doctor approval step.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime


AGENT_VERSION = "2026.04.30-integration-agents"


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
