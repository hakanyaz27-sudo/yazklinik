"""Shared YazKlinik feature and route manifest.

This module is deliberately small and stdlib-only.  The Flask web app,
the hybrid desktop shell, and the native WebShell import this same manifest
so menu additions/removals are made in one place instead of drifting across
surfaces.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Iterable


MANIFEST_VERSION = "2026.05.19-D700-FULL-FEATURE-ACCESS"

SURFACES = ("web", "desktop_hybrid", "webshell")
DESKTOP_MODES = ("shell", "hybrid", "mirror")

MENU_CATEGORIES = (
    {"key": "today", "label": "Bugun"},
    {"key": "patient", "label": "Hasta"},
    {"key": "clinical", "label": "Klinik"},
    {"key": "media", "label": "Goruntu"},
    {"key": "ai", "label": "YZ"},
    {"key": "system", "label": "Sistem"},
)

MENU_MODES = ("simple", "doctor", "advanced")

# Basit mod: doktorun gun icinde en cok bastigi rutin akislar.
SIMPLE_ROUTINE_ROUTES = {
    "/",
    "/dashboard",
    "/komuta-merkezi",
    "/kullanim-kalitesi",
    "/gun-plani",
    "/yeni-hasta",
    "/arama",
    "/hasta/{patient}",
    "/hasta/{patient}/hasta-dosyasi",
    "/hasta/{patient}/gelisler",
    "/hasta/{patient}/tahliller",
    "/hasta/{patient}/tetkik-istemi",
    "/hasta/{patient}/recete-hazirla",
    "/hasta/{patient}/sesli-recete",
    "/hasta/{patient}/konusarak-not",
    "/hasta/{patient}/gebelik-takip-plani",
    "/hasta/{patient}/gebelik-gelisim-takibi",
    "/hasta/{patient}/yz-diyet",
    "/hasta/{patient}/pdf-editor",
    "/hasta/{patient}/pdf-atolyesi",
    "/hasta/{patient}/rapor-pdf-yazdir",
    "/hizli-not",
    "/randevular",
    "/randevu/yeni",
    "/takvim",
    "/gorevler",
    "/akilli-bildirimler",
    "/jinekoloji",
    "/obstetrik",
    "/riskli-gebelik",
    "/medikal-estetik",
    "/doguranlar",
    "/gebe-takip",
    "/takip-medya-arsivi",
    "/dicom",
    "/dicom?mode=ai",
    "/dicom-servisleri",
    "/dicom-alisveris",
    "/dicom-worklist",
    "/hd-studio",
    "/hasta/{patient}/dosya-gezgini",
    "/hasta/{patient}/dicom-medya",
    "/hasta/{patient}/takip-medya",
    "/hasta/{patient}/dicom",
    "/akilli-rehber",
    "/akilli-dialog",
    "/sessiz-alex",
    "/bilgi-ajanlari",
    "/alex-arastirma",
    "/alex-egitim",
    "/yz-asistan",
    "/yz-komut-merkezi",
    "/medgemma-klinik-yz",
    "/medgemma-modul",
    "/yz-telefon-diyalog",
    "/sesli-recete",
    "/gun-sonu-ozeti",
    "/yz-sihirbazi",
    "/yz-server-durum",
    "/hizmet-ajanlari",
    "/terminal-cihaz-merkezi",
    "/entegrasyon/yz-telesekreter",
    "/entegrasyon-ajanlari",
    "/bulutklinik",
    "/enabiz",
    "/recete-sablonlari",
    "/onam-sablonlari",
    "/sohbet-merkezi",
    "/randevu-onay",
    "/sistem-durumu",
    "/altyapi-durumu",
    "/ayarlar",
    "/performans-ayarlari",
    "/sistem/dosya-konumlari",
    "/veritabani-saglik-kontrol",
    "/yedekleme-merkezi",
    "/sistem-guncelleme",
    "/cikis",
}

# Uzman mod: kurulum, entegrasyon, sistem ayari, yedek/onarim ve ileri PACS/YZ.
ADVANCED_EXPERT_ROUTES = {
    "/dicom-servisleri",
    "/dicom-alisveris",
    "/dicom-ayar",
    "/entegrasyonlar/usg-nas",
    "/online-chatgpt",
    "/islem-zincirleri",
    "/yz-sihirbazi",
    "/yz-kurulum-rehberi",
    "/yz-server-durum",
    "/entegrasyon/yz-telesekreter",
    "/bulutklinik-aktarim",
    "/entegrasyonlar",
    "/entegrasyon/ip-cihazlar",
    "/nas-senkronizasyon",
    "/whatsapp-ayarlari",
    "/terminal-cihaz-merkezi",
    "/ozellik-senkron",
    "/sistem-durumu-ozet",
    "/altyapi-durumu",
    "/ayarlar",
    "/performans-ayarlari",
    "/sistem/dosya-konumlari",
    "/veri-konumlari",
    "/tum-ayarlar",
    "/ayar-editoru",
    "/sistem-parametreleri",
    "/yazici-ayarlari",
    "/protokol-ayarlari",
    "/veritabani-saglik-kontrol",
    "/sistem-cache-temizle",
    "/audit-log",
    "/yedekleme-merkezi",
    "/otomatik-yedekler",
    "/otomatik-yedek/simdi-al",
    "/sistem-format",
    "/sistem-guncelleme",
    "/sistem-sifirla",
    "/temiz-kurulum",
    "/kurulum-sihirbazi",
    "/ilk-kurulum",
    "/export/hastalar.csv",
    "/export/randevular.csv",
    "/kullanici-ekle",
    "/sifre-degistir",
}


DOCTOR_WORKFLOW_ROUTES = {
    "/bulutklinik",
    "/enabiz",
    "/entegrasyon-ajanlari",
    "/sistem-durumu",
    "/altyapi-durumu",
    "/hasta-portal",       # D700: doktor menude direkt eriskin (Yeni Magic-Link)
    "/yz-konsultasyon",
    "/ceviri-merkezi",
    "/instagram-hazirla",
    "/mobil",
}


def _route_menu_mode(row: dict) -> str:
    route = str(row.get("route") or "")
    if route in SIMPLE_ROUTINE_ROUTES or row.get("simple"):
        return "simple"
    if route in DOCTOR_WORKFLOW_ROUTES:
        return "doctor"
    if route in ADVANCED_EXPERT_ROUTES:
        return "advanced"
    if row.get("category") == "system":
        return "advanced"
    return "doctor"


def _with_menu_mode(row: dict) -> dict:
    item = deepcopy(row)
    mode = _route_menu_mode(item)
    item["mode"] = mode
    item["simple"] = mode == "simple"
    item["doctor"] = mode in {"simple", "doctor"}
    item["advanced"] = mode == "advanced"
    return item


def _normalize_menu_mode(mode: str) -> str:
    mode = str(mode or "").strip().lower()
    if mode in MENU_MODES:
        return mode
    if mode in {"basit", "simple"}:
        return "simple"
    if mode in {"doktor", "doctor"}:
        return "doctor"
    if mode in {"uzman", "expert", "advanced"}:
        return "advanced"
    return "advanced"


def _route_visible_in_menu_mode(row: dict, mode: str) -> bool:
    item = _with_menu_mode(row)
    mode = _normalize_menu_mode(mode)
    if mode == "simple":
        return bool(item.get("simple"))
    if mode == "doctor":
        return bool(item.get("doctor"))
    return True


def _r(
    route: str,
    label: str,
    hint: str,
    category: str,
    icon: str,
    *,
    simple: bool = False,
    webshell: bool = True,
    desktop: bool = True,
    web: bool = True,
    aliases: Iterable[str] = (),
) -> dict:
    surfaces = []
    if web:
        surfaces.append("web")
    if desktop:
        surfaces.append("desktop_hybrid")
    if webshell and "{patient}" not in route:
        surfaces.append("webshell")
    return {
        "route": route,
        "label": label,
        "hint": hint,
        "category": category,
        "icon": icon,
        "simple": bool(simple),
        "patient_required": "{patient}" in route,
        "surfaces": surfaces,
        "aliases": list(aliases),
    }


FEATURE_GROUPS = (
    ("ANA", (
        _r("/tum-ozellikler", "Tum Ozellikler", "Programdaki tum kullanici ekranlari ve sonradan eklenen moduller", "today", "[ALL]",
           simple=True, aliases=("tum ozellikler", "tum menuler", "ozellikler", "feature catalog", "menu katalog")),
        _r("/ozellikler", "Ozellikler Alias", "Tum Ozellikler sayfasi alias", "today", "[ALL]",
           simple=True, aliases=("ozellikler", "tum ozellikler")),
        _r("/", "Hastalar", "Hasta listesi ve arama", "patient", "[A]", simple=True),
        _r("/hastalar", "Hastalar Listesi", "Hasta listesi ve arama alias", "patient", "[HL]", simple=True),
        _r("/akilli-sonuc-yukle", "Akilli Sonuc Yukleme", "PDF/Word/ekran goruntusunu akilli hasta arama ile dogru bolume yukle", "patient", "[SY]",
           simple=True, aliases=("sonuc yukle", "akilli sonuc", "nipt yukle", "smear yukle", "tetkik yukle", "pdf yukle")),
        _r("/menu-ara", "Menu Arama", "Tum menulerde hizli arama", "today", "[ARA]", simple=True,
           aliases=("menu bul", "fonksiyon ara", "ozellik ara")),
        _r("/dashboard", "Dashboard", "Klinik ana ekran", "today", "[P]", simple=True),
        _r("/komuta-merkezi", "Komuta Merkezi", "Klinik komuta paneli", "today", "[K]", simple=True),
        _r("/kullanim-kalitesi", "Klinik Akis", "Pratik kalite merkezi", "today", "[Q]", simple=True),
        _r("/gun-plani", "Gun Plani", "Bugunun akisi", "today", "[G]", simple=True),
        _r("/gunluk-ozet", "Gunluk Ozet", "Gunluk klinik ozet", "today", "[O]"),
        _r("/aylik-rapor", "Aylik Rapor", "Aylik istatistik raporu", "today", "[R]"),
        _r("/istatistikler", "Istatistikler", "Klinik sayilar ve grafikler", "today", "[I]"),
    )),
    ("HASTA", (
        _r("/yeni-hasta", "Yeni Hasta", "Kayit olustur", "patient", "+", simple=True),
        _r("/arama", "Arama", "Hasta ve kayit arama", "patient", "?", simple=True),
        _r("/gelismis-arama", "Gelismis Arama", "Detayli hasta arama", "patient", "??"),
        _r("/hasta/{patient}", "Hasta Ã–zeti", "SeÃ§ili hasta kartÄ±", "patient", "[H]", webshell=False, simple=True),
        _r("/hasta/{patient}/hasta-dosyasi", "Hasta Dosyasi", "PDF ve klinik hasta dosyasi", "patient", "[F]", webshell=False),
        _r("/hasta/{patient}/gelisler", "Gelisler", "Hasta gelisleri", "patient", "[G]", webshell=False),
        _r("/hasta/{patient}/zaman-cizgisi", "Zaman Cizgisi", "Hasta olay gecmisi", "patient", "[Z]", webshell=False),
        _r("/hasta/{patient}/yakinlar", "Hasta Yakinlari", "Aile ve acil iletisim", "patient", "[Y]", webshell=False),
        _r("/jinekoloji", "Jinekoloji", "Jinekolojik modul", "clinical", "[J]", simple=True),
        _r("/obstetrik", "Obstetrik", "Gebelik takibi", "clinical", "[O]", simple=True),
        _r("/riskli-gebelik", "Riskli Gebelik Takip Merkezi", "Yuksek risk ve kritik gebelik izlemi", "clinical", "[R]", simple=True),
        _r("/medikal-estetik", "Medikal Estetik", "Estetik hasta akisi", "clinical", "[M]", simple=True),
        _r("/doguranlar", "Dogumlar", "Dogum kayitlari", "clinical", "[D]", simple=True),
        _r("/yaklasan-dogumlar", "Yaklasan Dogumlar", "Yaklasan dogum listesi", "clinical", "[Y]"),
        _r("/gebe-takip", "Gebe Hasta Takibi", "Secilen tarihte tum gebelerin gebelik haftasi - doktor/tarih filtreli, siralanabilir", "clinical", "[GH]",
           simple=True, aliases=("gebe takip", "gebe hastalar", "gebelik haftalari", "kac haftalik", "tum gebeler", "gebe liste", "haftalik gebe")),
        _r("/karsilastir", "Karsilastir", "Hasta/olcum karsilastirma", "clinical", "<>"),
        _r("/hasta-merge", "Hasta Birlestir", "Mukerrer kayitlari tek hastada birlestir", "patient", "[BR]",
           simple=True, aliases=("merge", "birlestir", "ayni hasta", "duplicate")),
        _r("/arsivlenmis-hastalar", "Arsivlenmis Hastalar", "Silinen/arsivlenen hasta listesi + geri al", "patient", "[AR]",
           simple=True, aliases=("arsiv", "silinen", "deleted", "archived", "geri al")),
        _r("/fetal-buyume", "Fetal Buyume Grafigi", "Hadlock + Intergrowth-21st percentil egrisi (BPD/HC/AC/FL/EFW)", "clinical", "[FB]",
           simple=True, aliases=("fetal", "buyume", "biometri", "hadlock", "iugr", "makrozomi", "percentil")),
        _r("/servikal-uzunluk", "Servikal Uzunluk", "Preterm risk takibi - CL trend + cerclage onerisi", "clinical", "[CL]",
           simple=True, aliases=("servikal", "cervical", "cl", "preterm", "cerclage", "kisa serviks")),
        _r("/postpartum-takvim", "Postpartum Otomatik Takvim", "Dogum +6 hafta otomatik kontrol + PHQ-9 + kontrasepsiyon", "clinical", "[PT]",
           simple=True, aliases=("postpartum", "dogum sonrasi", "lohusalik", "6 hafta", "phq9")),
        _r("/kasa-dashboard", "Kasa Dashboard", "Bugun/hafta/ay gelir + bekleyen alacaklar + 30g trend", "system", "[KD]",
           simple=True, aliases=("kasa", "gelir", "tahsilat", "finans", "ciro", "para")),
        _r("/triaj-bot", "AI Triaj Bot", "WhatsApp mesaji yapistir -> aciliyet skoru 1-5 + aksiyon", "ai", "[TB]",
           simple=True, aliases=("triaj", "triage", "aciliyet", "wa triaj", "mesaj triaji")),
        _r("/public-randevu-istekleri", "Public Randevu Talepleri", "Public /randevu-al sayfasindan gelen talepler", "patient", "[PR]",
           simple=True, aliases=("public talep", "online randevu", "internet randevu")),
        _r("/randevu-al", "Public Randevu Sayfasi (Test)", "Hastalarin actigi public sayfa - test goruntule", "patient", "[RA]",
           aliases=("public randevu", "online booking")),
        _r("/sesli-not", "Sesli Visit Note", "Mikrofona konus -> Turkce metin -> hastaya kaydet", "ai", "[SN]",
           simple=True, aliases=("sesli not", "sesli muayene", "dikta", "transkripsiyon", "whisper not", "voice note")),
        _r("/ziyaret-sablonlari", "Ziyaret Sablonlari", "Hazir muayene sablonlari (Ilk gebe, PCOS, Postpartum vb)", "clinical", "[ZS]",
           simple=True, aliases=("sablon", "template", "muayene sablon", "ziyaret hazir")),
        _r("/ob-wheel", "OB-Wheel Gebelik Milestone", "LMP -> tum tarihler (NT, anomali, GDM, GBS, EDD)", "clinical", "[OB]",
           simple=True, aliases=("ob wheel", "gebelik takvim", "lmp", "edd", "milestone", "gestasyon")),
        _r("/etiketler", "Hasta Etiketleri", "VIP, Akraba, Sigortali vb tag yonetimi", "patient", "[ET]",
           simple=True, aliases=("etiket", "tag", "vip", "akraba", "label")),
        _r("/hatirlat-listesi", "Hatirlatma Listesi", "Bugun + 7 gun aranacak/hatirlatilacak hastalar", "patient", "[HL]",
           simple=True, aliases=("hatirlat", "recall", "geri ara", "follow up", "tekrar ara")),
        _r("/qr-klinik", "QR Klinik Duvari", "A4 QR kod yazdir - hasta tarar, portala girer", "system", "[QR]",
           simple=True, aliases=("qr", "qr kod", "duvar", "klinik girisi", "qr poster")),
        _r("/hasta-portal/self-giris", "Hasta Self-Giris (Public)", "TC+tel ile otomatik magic-link - QR hedefi", "patient", "[SG]",
           aliases=("self giris", "self service", "tc tel giris", "qr hedef")),
        _r("/ui-demo", "UI Polish Demo", "Yeni UI ozelliklerini test et (toast, modal, icon, font)", "system", "[UI]",
           simple=True, aliases=("ui demo", "polish demo", "toast test", "modal test")),
    )),
    ("MUAYENE", (
        _r("/hizli-not", "Hizli Not", "Aninda not", "today", "[N]", simple=True),
        _r("/randevular", "Randevular", "Liste gorunumu", "today", "[R]", simple=True),
        _r("/takvim", "Takvim", "Takvim gorunumu", "today", "[T]", simple=True),
        _r("/randevu/yeni", "Yeni Randevu", "Yeni randevu olustur", "today", "+"),
        _r("/toplu-hatirlatma", "Toplu Hatirlatma", "Randevu hatirlatmalari", "today", "[H]"),
        _r("/gorevler", "Gorevler", "Is listesi", "today", "[G]", simple=True),
        _r("/gorev/yeni", "Yeni Gorev", "Yeni gorev olustur", "today", "+"),
        _r("/akilli-bildirimler", "AkÄ±llÄ± Bildirim", "Sistemin tespit ettiÄŸi uyarÄ±lar", "today", "[B]", simple=True),
    )),
    ("KLINIK", (
        _r("/hasta/{patient}/gebelik-takip-plani", "Gebelik Takip", "A4 tarihli takip formu", "clinical", "[GT]", webshell=False),
        _r("/hasta/{patient}/gebelik-gelisim-takibi", "Gebelik Gelisim", "PDF USG buyume grafikleri", "clinical", "[GG]", webshell=False),
        _r("/hasta/{patient}/tahliller", "Tahliller", "Hasta tahlil dosyalari", "clinical", "[T]", webshell=False),
        _r("/gama-lab-ajani", "Gama Tip Lab Ajani", "Gama Tip portalindan sonucu alip hastaya eslestirir", "clinical", "[GL]",
           simple=True, aliases=("gama", "gama tip", "lab ajani", "laboratuvar ajani", "sonuc cek")),
        _r("/hasta/{patient}/tetkik-istemi", "Tetkik Istemi", "Tetkik istem formu", "clinical", "[TI]", webshell=False),
        _r("/hasta/{patient}/recete-hazirla", "ReÃ§ete", "2 harften ilaÃ§/tanÄ± bulan reÃ§ete ekranÄ±", "clinical", "[RX]", webshell=False),
        _r("/hasta/{patient}/sesli-recete", "Sesli ReÃ§ete", "SeÃ§ili hastaya sesli reÃ§ete", "ai", "[SR]", webshell=False),
        _r("/hasta/{patient}/konusarak-not", "KonuÅŸarak Not", "Mikrofonla hasta notu", "ai", "[KN]", webshell=False),
        _r("/hasta/{patient}/yz-recete-oner", "YZ ReÃ§ete", "ReÃ§ete Ã¶neri kontrolÃ¼", "ai", "[YR]", webshell=False),
        _r("/hasta/{patient}/yz-diyet", "Diyet", "Hasta diyet listesi", "clinical", "[DY]", webshell=False),
        _r("/onam-sablonlari", "Onam Sablonlari", "Database onam kutuphanesi", "clinical", "[O]", simple=True),
        _r("/recete-sablonlari", "HazÄ±r ReÃ§eteler", "Database reÃ§ete kÃ¼tÃ¼phanesi", "clinical", "[R]", simple=True),
        _r("/kontrol-listesi/menu", "Kontrol Listeleri", "Muayene checklist", "clinical", "[C]"),
        _r("/araclar", "Tum Araclar", "Klinik hesaplayicilar", "clinical", "[A]"),
        _r("/araclar/bmi-hesapla", "BMI", "BMI hesaplayici", "clinical", "[B]"),
        _r("/araclar/gebelik-hesapla", "Gebelik", "Gebelik hesaplayici", "clinical", "[G]"),
        _r("/araclar/fetal-tartim", "Fetal Tartim", "Fetal agirlik hesaplayici", "clinical", "[F]"),
        _r("/araclar/bishop-skoru", "Bishop", "Bishop skoru", "clinical", "[B]"),
        _r("/araclar/preeklampsi-risk", "Preeklampsi", "Preeklampsi risk araci", "clinical", "[P]"),
        _r("/araclar/ilac-rehberi", "Ilac Rehberi", "Ilac ve gebelik rehberi", "clinical", "[I]"),
        _r("/araclar/karar-agaci", "Karar Agaci", "Klinik karar agaci", "clinical", "[K]"),
        _r("/dogum-geri-sayim", "Dogum Geri Sayim", "Doguma kalan sure", "clinical", "[D]"),
        # === D128 yeni klinik moduller ===
        _r("/obgyn-rehber", "OB/GYN Klinik Rehber", "Textbook 11 kategori (gebelik, perinatoloji, IVF, onkoloji, vs)", "clinical", "[REH]", simple=True, aliases=("rehber", "textbook", "kadin dogum rehber")),
        _r("/ilac-piyasa", "Turkiye Ilac Marka", "110+ jenerik -> 400+ Turkiye marka adi (Rocephin, Mirena, Femara vs)", "clinical", "[ILC]", simple=True, aliases=("piyasa ilac", "marka", "jenerik")),
        _r("/diyet-rehberi", "Profesyonel Diyet", "Gebelik / GDM / PCOS / IVF / postpartum / menopoz / anemi (8 senaryo)", "clinical", "[DYT]", simple=True, aliases=("beslenme", "diyet")),
        _r("/gebelik-plani", "Hastaya Ozel Gebelik Plani", "SAT bazli 40 hafta kisisel takvim (yazdirilabilir)", "clinical", "[GBP]", simple=True, aliases=("gebelik takvim", "naegele")),
        _r("/ivf-konsult", "IVF Super Destek", "AMH/AFC/yas -> protokol + OHSS + Gardner + hCG kinetigi", "clinical", "[IVF]", simple=True, aliases=("tup bebek", "ivf konsult")),
        _r("/ovulasyon-induksiyon", "Ovulasyon Induksiyonu", "Letrozol/klomifen/gonadotropin protokol + cycle takvim", "clinical", "[OI]", simple=True, aliases=("yumurtlatma", "oi protokol")),
        _r("/anormal-uterin-kanama", "Anormal Uterin Kanama (AUB)", "FIGO PALM-COEIN siniflama + akut/kronik tedavi", "clinical", "[AUB]", aliases=("menometroraji", "aub")),
        _r("/endometrial-hiperplazi", "Endometrial Hiperplazi", "WHO 2014 atipisiz/atipili (EIN) tedavi", "clinical", "[HIP]", aliases=("hiperplazi", "ein")),
        _r("/pelvik-enfeksiyon", "Pelvik Enfeksiyon & Vajinit", "AkÄ±ntÄ± rengi -> tanÄ± + 8 mixt enfeksiyon protokolÃ¼", "clinical", "[PID]", simple=True, aliases=("vajinit", "pid")),
        _r("/ilac-guvenlik", "Ilac Guvenligi", "Gebelikte ilac kategori + ilac-ilac etkilesim + protokoler", "clinical", "[GUV]", simple=True, aliases=("recete kontrol", "gebelikte ilac")),
        _r("/tedavi-planla", "Tedavi PlanlayÄ±cÄ± (Super)", "Hasta autocomplete + protokol + DDI etkileÅŸim + A5 reÃ§ete + QR + PDF", "clinical", "[RX+]", simple=True, aliases=("recete yardimcisi", "ilac onerisi", "tedavi onerisi", "tedavi super", "rx super")),
        _r("/hasta-birlestir", "Hasta Birlestir (Merge)", "Iki hasta ayni kisiyse tek hastaya birlestir - tum visits/PDF/USG/recete tasinir, source arsivlenir", "patient", "[MRG]", aliases=("hasta merge", "birlestir", "ayni hasta", "tek hasta")),
        _r("/sistem-ayarlari", "Sistem AyarlarÄ± (D700)", "NAS yolu (\\\\asustor\\Voluson), lokal DB, port - config.env editleyici", "system", "[CFG]", aliases=("ayar", "config", "nas degistir", "db path", "yk-ayarlar")),
        _r("/gebelik-komplikasyon", "Gebelik Komplikasyon", "Hiperemezis/abortus/ektopik/mol/PPH/HELLP acil yonetim", "clinical", "[KMP]", aliases=("obstetrik acil",)),
    )),
    ("USG_GORUNTU", (
        _r("/dicom", "DICOM/PACS", "Orthanc ve gÃ¶rÃ¼ntÃ¼", "media", "[D]", simple=True),
        _r("/dicom?mode=ai", "DICOM / USG Zeka", "Orthanc, viewer, olcum ve AI merkezi", "media", "[DZ]", simple=True, aliases=("dicom ai", "usg zeka", "orthanc ai")),
        _r("/dicom-servisleri", "DICOM Servisleri", "Orthanc plugin merkezi", "media", "[S]", simple=True),
        _r("/dicom-alisveris", "DICOM Alisveris", "Voluson Worklist, C-STORE ve C-ECHO akisi", "media", "[X]", simple=True, aliases=("voluson", "worklist", "pacs alisveris")),
        _r("/dicom-worklist", "DICOM Worklist", "DICOM is listesi", "media", "[W]"),
        _r("/dicom-ayar", "DICOM Ayar", "Orthanc ve PACS parametreleri", "system", "[A]"),
        _r("/kamera", "Kamera / NVR", "Ic ag NVR panelini 5443 uzerinden proxy ile izle", "media", "bi bi-camera-video", simple=True, aliases=("kamera", "nvr", "ip kamera", "guvenlik kamera")),
        _r("/hd-studio", "HD Studio", "SeÃ§ili hastanÄ±n HD Live USG resim/video iyileÅŸtirme ekranÄ±", "media", "[HD]", simple=True, aliases=("hd studio", "usg", "mp4", "video")),
        _r("/bebek-goruntu-zeka", "Bebek YZ", "Lokal bebek/USG anomali Ã¶n tarama ve kalite artÄ±rma", "media", "[BZ]", simple=True, aliases=("bebek", "anomali", "kalite", "fetal")),
        _r("/takip-medya-arsivi", "Medya Arsivi", "Oncesi/sonrasi medya", "media", "[M]", simple=True),
        _r("/hasta/{patient}/takip-medya", "Medya", "Hasta medya takibi", "media", "[M]", webshell=False),
        _r("/hasta/{patient}/takip-medya?module=medical_aesthetic", "Medikal Estetik Medya", "Estetik medya akisi", "media", "[ME]", webshell=False),
        _r("/hasta/{patient}/dosya-gezgini", "NAS/DICOM Gezgin", "Hasta klasoru ve DICOM gezgini", "media", "[N]", webshell=False),
        _r("/hasta/{patient}/dicom-medya", "DICOM Medya", "Hasta DICOM medya", "media", "[DM]", webshell=False),
        _r("/hasta/{patient}/dicom", "DICOM / USG Zeka", "Orthanc eslestirme, OCR olcum ve AI on inceleme", "media", "[DZ]", webshell=False, simple=True, aliases=("usg zeka", "dicom zeka", "orthanc ai", "olcum")),
        _r("/dicom?patient={patient}", "Hasta DICOM/PACS", "SeÃ§ili hastanÄ±n DICOM gÃ¶rÃ¼ntÃ¼sÃ¼", "media", "[P]", webshell=False),
        _r("/hasta/{patient}/yz-resim-iyilestir", "HD Studio", "HD Live USG resim/video iyilestirme", "media", "[HD]", webshell=False, simple=True, aliases=("usg", "mp4", "video")),
        _r("/hasta/{patient}/pdf-editor", "PDF Rapor Editoru", "Rapor duzenleme", "media", "[PDF]", webshell=False),
        _r("/hasta/{patient}/pdf-atolyesi", "PDF Atolyesi", "Program ici PDF islemleri", "media", "[PA]", webshell=False),
        _r("/hasta/{patient}/rapor-pdf-yazdir", "PDF Yazdir", "Son PDF raporu yazdir", "media", "[PY]", webshell=False),
        _r("/ekran-yakala", "Ekran Yakala", "OCR + YZ", "media", "[E]", simple=True),
        _r("/entegrasyonlar/usg-nas", "USG NAS", "USG/NAS aktarÄ±m ayarlarÄ±", "media", "[N]"),
    )),
    ("YZ Asistanlar", (
        _r("/yz-asistan", "YZ Asistan", "Klinik asistan", "ai", "bi bi-robot", simple=True),
        _r("/akilli-rehber", "AkÄ±llÄ± Rehber", "Yol gÃ¶sterici asistan", "ai", "bi bi-compass", simple=True),
        _r("/yz-komut-merkezi", "YZ Komut", "Sesli/yazÄ±lÄ± komut merkezi", "ai", "bi bi-terminal", simple=True),
        _r("/hasta/{patient}/akilli-asistan", "Hasta AkÄ±llÄ± Asistan", "HafÄ±za, not, reÃ§ete ve risk Ã¶zeti", "ai", "bi bi-person-vcard", webshell=False),
        _r("/hasta/{patient}/hafiza", "Hasta HafÄ±zasÄ±", "Alerji, risk ve Ã¶nemli not kartlarÄ±", "ai", "bi bi-journal-medical", webshell=False),
    )),
    ("Ses ve AkÄ±llÄ± Diyalog", (
        _r("/ses-ve-alex", "Ses ve Alex Merkezi", "AkÄ±llÄ± Diyalog, sesli gÃ¶rÃ¼ÅŸme ve ses ayarlarÄ± tek yerde", "ai", "bi bi-mic-fill", simple=True, aliases=("ses merkezi", "alex ses", "akilli dialog ses")),
        _r("/akilli-dialog", "AkÄ±llÄ± Diyalog", "ChatGPT gibi konuÅŸan ve iÅŸ yapan ajan", "ai", "bi bi-chat-dots", simple=True),
        _r("/sessiz-alex", "Sessiz Alex", "Klavye ile sessiz AkÄ±llÄ± Diyalog", "ai", "bi bi-keyboard", simple=True, aliases=("sessiz dialog", "klavye alex", "yazarak alex")),
        _r("/bilgi-ajanlari", "Bilgi AjanlarÄ±", "PubMed + gÃ¼venilir web bilgisini kaynaklÄ± YAZ hafÄ±zasÄ±na iÅŸler", "ai", "bi bi-broadcast", simple=True, aliases=("yaz llm", "webden ogren", "webden Ã¶ÄŸren", "kaynakli bilgi", "kaynaklÄ± bilgi", "bilgi ajanlari")),
        _r("/alex-arastirma", "Alex AraÅŸtÄ±rma", "PubMed + web online arama, TÃ¼rkÃ§e Ã¶zet + klinik Ã¶neri", "ai", "bi bi-search-heart", simple=True, aliases=("pubmed", "literatur tara", "online arastir", "alex arastirma", "tibbi arastirma")),
        _r("/alex-egitim", "Alex EÄŸitim", "Alex'e kalÄ±cÄ± bilgi Ã¶ÄŸret + Ã¶zel komut (Windows aksiyon) tanÄ±mla", "ai", "bi bi-mortarboard-fill", simple=True, aliases=("alex egit", "ogret", "hafiza yonet", "komut tanimla")),
        _r("/alex-hafiza", "Alex HafÄ±zasÄ±", "KonuÅŸma, klavye ve eÄŸitimlerden Yaz LLM ile Ã¶ÄŸrenilen kalÄ±cÄ± hafÄ±za", "ai", "bi bi-journal-text", simple=True, aliases=("alex hafiza", "ne ogrendin", "benden ne ogrendin", "yaz llm hafiza", "kalici hafiza")),
        _r("/sesli-recete", "Sesli ReÃ§ete", "KonuÅŸarak reÃ§ete taslaÄŸÄ±", "ai", "bi bi-mic", simple=True),
        _r("/hizmet-ajanlari", "Hizmet AjanlarÄ±", "Randevu, hasta takip, reÃ§ete, BK-Voluson ve Alex ajanlarÄ±", "ai", "bi bi-person-workspace", simple=True, aliases=("benim ajanlarim", "ajanlarim", "hizmet eden ajanlar", "calisan ajanlar")),
        _r("/yz-ses-cevir", "Ses Ã‡evir", "Sesli notu metne Ã§evir", "ai", "bi bi-soundwave"),
        _r("/ses-profilleri", "Alex Ses SeÃ§imi", "Alex konuÅŸma sesi ve ses profilleri", "ai", "bi bi-volume-up", simple=True, aliases=("ses profilleri", "alex sesi", "tts")),
        _r("/mikrofon-tani", "Mikrofon TanÄ±", "Mikrofon ve ses sistemi testi", "ai", "bi bi-mic-mute", simple=True, aliases=("mikrofon", "ses testi")),
        _r("/yz-telefon-diyalog", "Telefon Diyalog", "TÃ¼rkÃ§e telefon sohbeti", "ai", "bi bi-telephone", simple=True),
        _r("/entegrasyon/yz-telesekreter", "YZ Telesekreter", "IP telefon/PBX", "ai", "bi bi-telephone-inbound", simple=True),
    )),
    ("YZ Analiz ve Otomasyon", (
        _r("/yz-tahlil-yorumla", "Tahlil Yorum", "Tahlil yorumlama", "ai", "bi bi-clipboard2-pulse"),
        _r("/islem-zincirleri", "Ä°ÅŸlem Zincirleri", "ReÃ§ete, randevu ve WhatsApp taslaklarÄ±", "ai", "bi bi-diagram-3", simple=True),
        _r("/gun-sonu-ozeti", "GÃ¼n Sonu Ã–zeti", "GÃ¼nlÃ¼k klinik Ã¶zet", "ai", "bi bi-moon-stars", simple=True),
        _r("/hasta/{patient}/gorsel-tani-destegi", "Resimle Ã–n TanÄ±", "Hasta resmiyle Ã¶n tanÄ± ve ilaÃ§ Ã¶n Ã¶nerisi", "ai", "bi bi-image", webshell=False),
        _r("/hasta/{patient}/yz-anomali-tarama", "YZ Anomali", "USG anomali Ã¶n tarama", "ai", "bi bi-bounding-box", webshell=False),
        _r("/hasta/{patient}/yz-medya-analiz", "YZ Medya", "Hasta medya analizi", "ai", "bi bi-images", webshell=False),
    )),
    ("YZ Ayarlar", (
        _r("/online-chatgpt", "Online ChatGPT", "OpenAI + Ollama ayarlarÄ±", "ai", "bi bi-cloud-check", simple=True),
        _r("/yz-sihirbazi", "YZ SihirbazÄ±", "Model ve ayar yardÄ±mcÄ±sÄ±", "ai", "bi bi-magic", simple=True),
        _r("/yz-kurulum-rehberi", "YZ Kurulum", "YZ kurulum rehberi", "ai", "bi bi-rocket-takeoff"),
        _r("/yz-server-durum", "YZ Server", "Ollama durumu", "ai", "bi bi-hdd-network", simple=True),
        _r("/alex-egitim-merkezi", "Alex Egitim Merkezi (LLM)", "Dataset, Modelfile, LoRA fine-tune yonetimi", "ai", "bi bi-cpu",
           simple=True, aliases=("llm egitim", "modelfile", "lora", "fine tune", "dataset", "alex egitim merkezi")),
        _r("/akilli-mod", "Akilli Mod (AI Kurulum)", "Ollama + AI baglantilarini sihirbazla kur", "ai", "bi bi-magic",
           simple=True, aliases=("akilli mod", "ai kurulum", "ollama kur", "yz kurulum")),
    )),
    ("SABLONLAR", (
        _r("/wa-sablonlar", "WhatsApp Sablon", "WhatsApp mesaj sablonlari", "patient", "[W]"),
        _r("/hasta/{patient}/whatsapp", "WhatsApp", "Hasta WhatsApp mesaji", "patient", "[WA]", webshell=False),
        _r("/hasta/{patient}/onam", "Onam", "Hasta onam akisi", "clinical", "[ON]", webshell=False),
        _r("/onam-sablonlari?patient={patient}", "Hasta Onam Åablonu", "SeÃ§ili hasta onam ÅŸablonu", "clinical", "[OS]", webshell=False),
        _r("/recete-sablonlari?patient={patient}", "Hasta ReÃ§ete Åablonu", "SeÃ§ili hasta hazÄ±r reÃ§ete", "clinical", "[RS]", webshell=False),
    )),
    ("ENTEGRASYON", (
        _r("/bulutklinik", "BulutKlinik Ajani", "BulutKlinik resmi API connector", "system", "[BK]", simple=True, aliases=("bulutklinik", "cloud klinik")),
        _r("/bulutklinik-merkez", "BulutKlinik Merkez", "BulutKlinik kontrol paneli - durum + sync + log", "system", "[BM]",
           simple=True, aliases=("bk merkez", "bulutklinik panel", "cloud panel")),
        _r("/bk-hastalar", "BK Hastalar Listesi", "BulutKlinik'ten import edilen hastalar", "system", "[BH]",
           simple=True, aliases=("bk hasta", "bulutklinik hasta", "import hasta")),
        _r("/bk-voluson-match", "BK <-> Voluson Eslestirme", "BulutKlinik hastalari ile USG klasorleri eslestir", "system", "[BV]",
           simple=True, aliases=("bk voluson", "voluson match", "eslestir", "usg eslestir")),
        _r("/ajanlar", "Ajan Merkezi", "Calistirilabilir ajan paneli", "system", "[AM]",
           simple=True, aliases=("ajan", "ajan kontrol", "agent center")),
        _r("/enabiz", "e-Nabiz Ajani", "e-Nabiz hasta paylasimli PDF aktarim", "system", "[EN]", simple=True, aliases=("e-nabiz", "enabiz", "saglik bakanligi")),
        _r("/bulutklinik-aktarim", "Bulutklinik (eski)", "Eski bulutklinik aktarim sayfasi", "system", "[B]"),
        _r("/entegrasyon-ajanlari", "Ajan Ayarlari", "BulutKlinik, e-Nabiz, DoktorTakvimi ve KVKK ajan ayarlari", "system", "[AI]", simple=True, aliases=("bulutklinik", "enabiz", "doktor takvimi", "dis entegrasyon")),
        _r("/entegrasyonlar", "Entegrasyon Merkezi", "Pratik entegrasyon akis paneli", "system", "[E]", simple=True, aliases=("entegrasyon", "pdf destek", "destek programlari", "dis sistem")),
        _r("/entegrasyon/ip-cihazlar", "IP Cihazlar", "IP kamera/telefon/PBX", "system", "[IP]"),
        _r("/kamera-nvr", "Kamera/NVR Ayar", "Kamera/NVR ag ayarlari ve 5443 proxy", "system", "[KN]",
           simple=True, aliases=("kamera", "nvr", "ip kamera", "guvenlik kamera")),
        _r("/nas-senkronizasyon", "NAS Senkron", "NAS surucu senkronizasyonu", "system", "[N]"),
        _r("/whatsapp-ayarlari", "WhatsApp Ayar", "WhatsApp ayarlarÄ±", "system", "[W]"),
        _r("/wa-toplu", "WA Toplu", "Toplu WhatsApp islemleri", "patient", "[WT]"),
        _r("/telefon-ara", "Telefon Ara", "Telefon arama kisayolu", "patient", "[T]"),
        _r("/sohbet-merkezi", "Sohbet Merkezi", "Sohbet ve randevu talepleri", "patient", "[SOH]", simple=True),
        _r("/randevu-onay", "Randevu Onay", "YZ randevu taleplerini onayla", "patient", "[RO]", simple=True),
    )),
    ("SISTEM", (
        _r("/terminal-cihaz-merkezi", "Terminal/Cihaz", "Terminal, iPhone, Mac, medya ve WhatsApp istemci modu", "system", "bi bi-phone", simple=True, aliases=("terminal", "cihaz", "iphone", "mac", "whatsapp cihaz", "resim cihaz")),
        _r("/ozellik-senkron", "Hibrit/Web Senkron", "Ortak ozellik manifesti ve menu senkronizasyonu", "system", "[SYNC]", simple=True, aliases=("senkron", "sync")),
        _r("/sistem-durumu", "Sistem Durumu", "Server, YZ, DICOM ve depolama durumu", "system", "[D]", simple=True),
        _r("/altyapi-durumu", "Altyapi Guard", "Web, DB, NAS, Alex servisleri ve canli surec yonetimi", "system", "[AG]", simple=True, aliases=("altyapi", "guard", "stabilite")),
        _r("/sistem-durumu-ozet", "Sistem Ozet", "Terminal uyumlu sistem ozeti", "system", "[O]"),
        _r("/ayarlar", "Ayarlar", "Web ayarlarÄ±", "system", "[A]", simple=True),
        _r("/performans-ayarlari", "Performans", "RAM ve masaustu hiz modu", "system", "[P]", simple=True),
        _r("/sistem/dosya-konumlari", "Dosya Konumlari", "NAS, medya, cikti ve yedek yollari", "system", "[V]", simple=True),
        _r("/veri-konumlari", "Veri Konumlari", "Sistem dosya haritasi", "system", "[V]"),
        _r("/tum-ayarlar", "Tum Ayarlar", "Butun kontrol anahtarlari", "system", "[T]"),
        _r("/ayar-editoru", "Ayar Editor", "Uzman ayar editoru", "system", "[E]"),
        _r("/sistem-parametreleri", "Sistem Param", "YZ modelleri, port ve timeout", "system", "[S]"),
        _r("/yazici-ayarlari", "YazÄ±cÄ± Ayar", "YazÄ±cÄ± ve Ã§Ä±ktÄ± ayarlarÄ±", "system", "[P]"),
        _r("/protokol-ayarlari", "Protokol", "Protokol ayarlarÄ±", "system", "[P]"),
        _r("/veritabani-saglik-kontrol", "DB Saglik", "Veritabani kontrol, yedek, vacuum ve onarim", "system", "[DB]", simple=True),
        _r("/sistem-cache-temizle", "Cache Temizle", "Sistem cache temizleme", "system", "[C]"),
        _r("/audit-log", "Audit Log", "Denetim kayitlari", "system", "[L]"),
        _r("/yedekleme-merkezi", "Yedekleme", "Otomatik yedek ve geri alma merkezi", "system", "[Y]", simple=True),
        _r("/otomatik-yedekler", "Yedekler", "Otomatik yedek listesi", "system", "[Y]"),
        _r("/otomatik-yedek/simdi-al", "Simdi Yedek", "Aninda yedek al", "system", "[S]"),
        _r("/sistem-format", "Format", "Sistem format akisi", "system", "[F]"),
        _r("/sistem-guncelleme", "Guncelleme", "update.zip yukle", "system", "[G]", simple=True),
        _r("/sistem-sifirla", "Sifirla", "Sistem sifirlama", "system", "[0]"),
        _r("/temiz-kurulum", "Temiz Kurulum", "Sifirlama/format", "system", "[!]", simple=True),
        _r("/kurulum-sihirbazi", "Kurulum", "Sistem kurulum sihirbazi", "system", "[K]"),
        _r("/ilk-kurulum", "Ilk Kurulum", "Ilk kurulum sihirbazi", "system", "[I]"),
    )),
    ("EXPORT", (
        _r("/export/hastalar.csv", "Hastalar CSV", "Hasta CSV disari aktarim", "system", "[CSV]"),
        _r("/export/randevular.csv", "Randevular CSV", "Randevu CSV disari aktarim", "system", "[CSV]"),
    )),
    ("KULLANICI", (
        _r("/kullanici-ekle", "Kullanici Ekle", "Yeni kullanici", "system", "[K]"),
        _r("/sifre-degistir", "Sifre Degistir", "Kullanici sifresi", "system", "[S]"),
        _r("/yardim", "Yardim", "Yardim sayfasi", "system", "?"),
        _r("/cikis", "Cikis", "Oturumu kapat", "system", "[X]", simple=True),
    )),
    ("EK ERISIM VE ALIAS", (
        _r("/ayarlar/yapay-zeka", "Online YZ Ayarlari", "Claude, ChatGPT, DeepSeek, Gemini ve Ollama baglantilari", "ai", "[AI]",
           simple=True, aliases=("online yz", "chatgpt ayar", "claude ayar", "deepseek", "gemini")),
        _r("/ayarlar/dosya-yerleri", "Dosya Yerleri", "NAS, DB, multimedia ve Orthanc dosya yerleri", "system", "[DY]",
           simple=True, aliases=("dosya yerleri", "nas yol", "db yol", "orthanc")),
        _r("/app", "Web App Kabugu", "App/WebShell giris kabugu", "today", "[APP]",
           aliases=("app", "web app", "kabuk")),
        _r("/ui", "UI Kabugu", "UI/WebShell giris alias", "today", "[UI]",
           aliases=("ui", "web ui", "kabuk")),
        _r("/yapay-zeka", "Yapay Zeka Ayarlari", "YZ ayarlari alias", "ai", "[YZ]",
           aliases=("ai ayar", "yapay zeka")),
        _r("/yz-gorev-modelleri", "YZ Gorev Modelleri", "Her klinik gorev icin ayri model secimi", "ai", "[GM]",
           simple=True, aliases=("gorev modeli", "model gorev", "task model")),
        _r("/yz-sistem-onerileri", "YZ Sistem Onerileri", "Sistem icin YZ iyilestirme onerileri", "ai", "[YO]",
           aliases=("sistem onerisi", "ai onerileri")),
        _r("/yz-akilli-dialog", "YZ Akilli Diyalog", "Akilli dialog alias", "ai", "[AD]",
           aliases=("akilli sohbet alias", "yz dialog")),
        _r("/alex-baslat", "Alex Baslat", "Alex arka plan dinleme/servis baslatma", "ai", "[AB]",
           simple=True, aliases=("alex start", "alex ac")),
        _r("/alex-kapat", "Alex Kapat", "Alex arka plan dinleme/servis kapatma", "ai", "[AK]",
           aliases=("alex stop", "alex kapat")),
        _r("/benim-ajanlarim", "Benim Ajanlarim", "Hizmet ajanlari alias", "ai", "[BA]",
           simple=True, aliases=("ajanlarim", "benim ajanlarim")),
        _r("/akinti-protokol", "Akinti / PID Protokol", "Vajinit ve PID protokol alias", "clinical", "[AP]",
           simple=True, aliases=("akinti", "vajinit", "pid")),
        _r("/vajinit", "Vajinit", "Akinti protokol alias", "clinical", "[VJ]",
           aliases=("akinti", "vajinal enfeksiyon")),
        _r("/aub", "AUB Alias", "Anormal uterin kanama kisa yolu", "clinical", "[AUB]",
           aliases=("aub", "kanama")),
        _r("/menometroraji", "Menometroraji", "AUB alias", "clinical", "[MM]",
           aliases=("kanama", "menometroraji")),
        _r("/hiperplazi", "Hiperplazi Alias", "Endometrial hiperplazi kisa yolu", "clinical", "[HP]",
           aliases=("hiperplazi", "ein")),
        _r("/obstetrik-acil", "Obstetrik Acil Alias", "Gebelik komplikasyonlari kisa yolu", "clinical", "[OA]",
           simple=True, aliases=("obstetrik acil", "gebelik acil")),
        _r("/gebelikte-acil", "Gebelikte Acil", "Gebelik komplikasyonlari alias", "clinical", "[GA]",
           aliases=("gebelik acil", "acil gebelik")),
        _r("/perinatoloji", "Perinatoloji Alias", "Riskli gebelik/perinatoloji kisa yolu", "clinical", "[PN]",
           simple=True, aliases=("perinatoloji", "perinat")),
        _r("/yuksek-risk-gebelik", "Yuksek Risk Gebelik", "Riskli gebelik alias", "clinical", "[YR]",
           aliases=("yuksek risk", "riskli gebe")),
        _r("/diyabetik-gebe", "Diyabetik Gebe", "GDM/riskli gebelik alias", "clinical", "[DG]",
           aliases=("gdm", "diyabetik gebe")),
        _r("/gebelikte-ilac", "Gebelikte Ilac Alias", "Ilac guvenligi kisa yolu", "clinical", "[GI]",
           simple=True, aliases=("gebelikte ilac", "ilac guvenlik")),
        _r("/gebelik-takvim", "Gebelik Takvim Alias", "Gebelik plani kisa yolu", "clinical", "[GTK]",
           simple=True, aliases=("gebelik takvim", "takvim")),
        _r("/hasta-gebelik-plan", "Hasta Gebelik Plan Alias", "Gebelik plani kisa yolu", "clinical", "[HGP]",
           aliases=("hasta gebelik plan", "gebelik plan")),
        _r("/beslenme", "Beslenme Alias", "Diyet rehberi kisa yolu", "clinical", "[BES]",
           aliases=("beslenme", "diyet")),
        _r("/diyet", "Diyet Alias", "Diyet rehberi kisa yolu", "clinical", "[DY]",
           aliases=("diyet", "beslenme")),
        _r("/ilac-onerisi", "Ilac Onerisi", "Tedavi/recete onerisi kisa yolu", "clinical", "[IO]",
           simple=True, aliases=("ilac onerisi", "recete onerisi")),
        _r("/recete-kontrol", "Recete Kontrol", "Ilac guvenligi ve tedavi kontrol kisa yolu", "clinical", "[RK]",
           aliases=("recete kontrol", "ddi")),
        _r("/recete-yardimcisi", "Recete Yardimcisi", "Tedavi planlayici alias", "clinical", "[RY]",
           simple=True, aliases=("recete yardimcisi", "tedavi planla")),
        _r("/turkiye-ilaclari", "Turkiye Ilaclari", "Ilac piyasa alias", "clinical", "[TI]",
           aliases=("turkiye ilac", "ilac piyasa")),
        _r("/kadin-dogum-rehber", "Kadin Dogum Rehber", "OB/GYN rehber alias", "clinical", "[KD]",
           aliases=("kadin dogum rehber", "obgyn")),
        _r("/textbook", "Textbook Alias", "OB/GYN rehber kisa yolu", "clinical", "[TX]",
           aliases=("textbook", "rehber")),
        _r("/ivf-destek", "IVF Destek", "IVF konsult alias", "clinical", "[IVF]",
           simple=True, aliases=("ivf destek", "tup bebek")),
        _r("/tup-bebek", "Tup Bebek", "IVF konsult alias", "clinical", "[TB]",
           aliases=("tup bebek", "ivf")),
        _r("/oi-protokol", "OI Protokol", "Ovulasyon induksiyonu alias", "clinical", "[OI]",
           aliases=("oi", "ovulasyon")),
        _r("/yumurtlatma-tedavisi", "Yumurtlatma Tedavisi", "Ovulasyon induksiyonu alias", "clinical", "[YT]",
           aliases=("yumurtlatma", "ovulasyon")),
        _r("/embriyo-gelisimi", "Embriyo Gelisimi", "IVF/embriyo gelisim ekrani", "clinical", "[EM]",
           aliases=("embriyo", "ivf embriyo")),
        _r("/dicom/worklist", "DICOM Worklist Alias", "DICOM worklist kisa yolu", "media", "[DW]",
           aliases=("worklist", "dicom worklist")),
        _r("/dicom-web/", "DICOM Web Viewer", "DICOM web viewer kisa yolu", "media", "[DWEB]",
           aliases=("dicom web", "viewer")),
        _r("/ohif/", "OHIF Viewer", "OHIF DICOM viewer", "media", "[OHIF]",
           aliases=("ohif", "dicom viewer")),
        _r("/stone-webviewer/", "Stone Web Viewer", "Stone DICOM viewer", "media", "[STN]",
           aliases=("stone", "dicom viewer")),
        _r("/volview/", "VolView", "VolView DICOM/3D viewer", "media", "[VOL]",
           aliases=("volview", "3d viewer")),
        _r("/web-viewer/", "Web Viewer", "DICOM web viewer alias", "media", "[WV]",
           aliases=("web viewer", "dicom")),
        _r("/nvr", "NVR Alias", "Kamera/NVR kisa yolu", "media", "[NVR]",
           aliases=("nvr", "kamera")),
        _r("/voluson-import", "Voluson Import", "Voluson/NAS import kontrolu", "media", "[VI]",
           aliases=("voluson import", "usg import")),
        _r("/veri-cakismalari", "Veri Cakismalari", "Hasta verisi onay/cakisma merkezi", "system", "[VC]",
           simple=True, aliases=("veri onayi", "cakisma")),
        _r("/veridb-merkezi", "Veri DB Merkezi", "Veritabani merkezi", "system", "[VDB]",
           aliases=("veridb", "db merkezi")),
        _r("/veritabani-secimli-temizle", "Secimli DB Temizligi", "Guvenli secimli veritabani temizlik ekrani", "system", "[DT]",
           aliases=("db temizle", "secimli temizlik")),
        _r("/media-ram-cache/temizle", "Media RAM Cache Temizle", "Medya cache temizleme", "system", "[MC]",
           aliases=("ram cache", "media cache")),
    )),
    ("AJANLAR", (
        _r("/ajanlar", "Klinik Ajanlari", "44 ajan dashboard + manifest", "ai", "[AJ]",
           simple=True, aliases=("agents", "ajan paneli", "ajan merkezi")),
        _r("/medgemma-modul", "MedGemma Modul", "MedGemma ayar + saglik + analiz paneli", "ai", "[MGA]",
           simple=True, aliases=("medgemma modul", "medgemma ayar", "medgemma panel")),
        _r("/medgemma-klinik-yz", "MedGemma Klinik YZ", "Google MedGemma tabanli USG/PDF/lab/not uzman ajani", "ai", "[MG]",
           simple=True, aliases=("medgemma", "medikal llm", "klinik yz", "usg ai", "lab ai", "google medgemma")),
        _r("/yz-konsultasyon", "YZ Konsultasyon (5-step)", "Vaka -> kirmizi alarm + DDx + tedavi + takip", "ai", "[YK]",
           simple=True, aliases=("konsultasyon", "yz hekim", "tani plani", "konsult", "tani tedavi", "konsultan hekim", "vakaya bakis", "ai konsult", "yapay zeka hekim")),
        _r("/instagram-hazirla", "Instagram Hazirla", "USG arsivinden Instagram draft (KVKK)", "ai", "[IG]",
           simple=True, aliases=("instagram", "ig", "sosyal medya", "post hazirla")),
        _r("/ceviri-merkezi", "Tibbi Ceviri (PubMed)", "Ingilizce makale -> TR ceviri + ozet", "ai", "[TR]",
           simple=True, aliases=("ceviri", "translate", "pubmed", "ingilizce turkce", "makale ceviri")),
        _r("/yz-telefon-diyalog", "YZ Telesekreter", "Aramayi triyaj eder", "ai", "[TS]"),
        _r("/randevu-onay", "Sesli Randevu Onay", "Evet/hayir/ertele karari", "ai", "[SO]"),
        _r("/dicom?mode=ai", "USG Rapor Taslak", "Olcumden EFW+rapor", "ai", "[UR]"),
        _r("/toplu-hatirlatma", "Geri Cagirma", "Hatirlatma kuyrugu", "ai", "[GC]"),
        _r("/bulutklinik-merkez", "BK Sync Bekci", "BulutKlinik baglanti saglik", "ai", "[BS]"),
        _r("/yedekleme-merkezi", "NAS Yedek Izleyici", "Yedek+disk saglik", "ai", "[NY]"),
        _r("/recete-gunluk-kontrol", "Recete Taslak", "Gecmis+alerji ile recete", "ai", "[RT]"),
        _r("/gun-plani", "Gunluk Ozet", "Gun sonu klinik ozeti", "ai", "[GO]"),
        _r("/sistem-durumu", "Mojibake Bekci", "Encoding tespit (read-only)", "system", "[MB]"),
        _r("/calisan-isler", "PR Reviewer", "Diff sablon kontrol", "system", "[PR]"),
    )),
    # Session 7 - 14 yeni klinik AI sayfasi + Mobil + Compliance + Portal
    ("SESSION 7 (YENI)", (
        _r("/mobil", "Mobil Dashboard", "iPhone 17 Pro Max + iPad icin ozel tek-ekran panel", "ai", "[MB]",
           simple=True, aliases=("mobil", "telefon", "iphone", "ipad", "phone dashboard")),
        _r("/uyumluluk", "ISO 27001 + KVKK Uyumluluk", "Anlik grade A-F + eksik kontrol listesi", "system", "[UY]",
           simple=True, aliases=("compliance", "kvkk", "iso", "uyumluluk", "gdpr", "ozel veri")),
        _r("/status", "Sistem Durum (PUBLIC)", "10 servis canli mi - hastalara da gosterilebilir", "system", "[ST]",
           simple=True, aliases=("status", "uptime", "saglik", "servis durum", "calisior mu")),
        _r("/stok", "Stok Takip", "Ilac + sarf miat + azalan + sipariÅŸ onerisi", "system", "[SK]",
           simple=True, aliases=("stok", "ilac stok", "sarf", "envanter", "miat")),
        _r("/2fa-setup", "2FA Setup (TOTP)", "Google Authenticator ile 6 hane dogrulama kur", "system", "[2F]",
           simple=True, aliases=("2fa", "two factor", "totp", "google authenticator", "iki adimli")),
        _r("/hasta-portal?admin=1", "ğŸ”— Hasta Portal (Magic-Link)", "Hastaya WhatsApp ile USG/PDF/lab paylaÅŸ - SÃ¼resiz + TC dogrulama", "patient", "[HP]",
           simple=True, aliases=("hasta portal", "patient portal", "magic link", "self service", "hasta paylas", "usg paylas", "wp link uret", "whatsapp uret")),
        _r("/dicom?mode=ai", "USG Goruntu Analiz (AI)", "llama3.2-vision: modality + biyometri + IG", "ai", "[VU]"),
        _r("/yz-konsultasyon", "SOAP Genisletici", "2 satir not -> tam SOAP formati", "ai", "[SP]"),
        _r("/yz-konsultasyon", "ICD-10 Kod Oneren", "Tani metni -> en uygun 5 kod", "ai", "[IC]"),
        _r("/gebelik-plani", "Gebelik Takvimi", "LMP -> NT/morfo/GDM/GBS/dogum tarihleri", "clinical", "[GT]"),
        _r("/riskli-gebelik", "Preeklampsi Risk Skoru", "SBP/DBP/protein -> evre + tedavi onerisi", "clinical", "[PR]"),
        _r("/riskli-gebelik", "HELLP Risk (Mississippi)", "Hemoliz+AST+trombosit -> Class I/II/III", "clinical", "[HL]"),
        _r("/araclar/bishop-skoru", "Bishop Indukstion Skoru", "Servikal -> indukstion uygunluk", "clinical", "[BP]"),
        _r("/riskli-gebelik", "VTE Padua Skoru", "Yatan hasta tromboz riski + LMWH", "clinical", "[VT]"),
        _r("/ilac-guvenlik", "DDI Ilac Etkilesim", "Receteyi cift cift kontrol + gebelik kategori", "clinical", "[DD]",
           simple=True, aliases=("ilac etkilesim", "drug interaction", "ddi")),
        _r("/obgyn-rehber", "Smear/HPV Takip (ASCCP)", "ASCUS+HPV+ -> kolposkopi tarihi otomatik", "clinical", "[SH]"),
        _r("/ajanlar?agent=phq9", "PHQ-9 Depresyon Tarama", "9 soru postpartum depresyon + intihar uyarisi", "clinical", "[PQ]"),
        _r("/yz-konsultasyon", "Konsey Vaka Sunum", "Tumor board markdown slayt + RAG citation", "clinical", "[KS]"),
        _r("/hd-studio", "Hatira USG WhatsApp", "Guzel kareyi anneye anonim + watermark", "media", "[HU]"),
        _r("/akilli-dialog", "Voice Command", "'BPD 85', 'yeni hasta Ayse' regex parse", "ai", "[VC]"),
        _r("/gun-plani", "Anti-Burnout Dashboard", "Yorgunluk skoru + mola onerisi", "system", "[AB]"),
        _r("/yz-konsultasyon", "Multi-Agent Orchestrator", "Tam ziyaret zinciri (5 ajan tek tikla)", "ai", "[OR]"),
        _r("/hasta-portal?admin=1", "Magic-Link Uret", "Hasta self-service icin 24s gecerli link", "patient", "[ML]"),
        _r("/kasa-dashboard", "Iyzico/Stripe Odeme", "Kart tahsilat + 3D Secure + iade", "system", "[PY]"),
        _r("/calisan-isler", "Memnuniyet Anketi (Dun)", "Dun gelenlere 5-yildiz WhatsApp", "ai", "[MS]"),
        _r("/calisan-isler", "Dogum Gunu Tebrik (Bugun)", "Bugun dogan hastalara mesaj", "ai", "[BT]"),
        _r("/pubmed-tarama", "PubMed Tarama (Gunluk)", "8 sorgu yeni makale + RAG indeks", "ai", "[PC]"),
        _r("/pubmed-tarama", "PubMed Tarama (UI)", "Arka planda PubMed scan baslat + sonuc takip", "ai", "[PT]",
           simple=True, aliases=("pubmed", "literatur tarama", "makale tara", "yeni makale", "pubmed bg")),
        _r("/alex-rag-merkezi", "RAG Merkezi (Semantic)", "Vector DB + reindex + test search + dosya yukle", "ai", "[RG]",
           simple=True, aliases=("rag", "semantic search", "vector db", "embed", "rag merkezi", "alex rag")),
        _r("/calisan-isler", "Calisan Isler (BG-Jobs)", "Arka planda calisan tum islerin canli durum paneli", "system", "[CI]",
           simple=True, aliases=("bg job", "arka plan", "background", "calisan", "isler", "calisan isler")),
        _r("/entegrasyonlar", "Medula Provizyon (Stub)", "SGK sigorta sorgulama iskelet", "system", "[MD]"),
        _r("/entegrasyonlar", "Duzen Lab Sonuc (Stub)", "Hastanin lab sonucu cek", "clinical", "[LB]"),
        _r("/entegrasyon/ip-cihazlar", "IoT BT Cihaz Tara (Stub)", "Omron BP / Xiaomi tarti / Accu-Chek", "clinical", "[IO]"),
        _r("/ajanlar", "3rd Party Plugin Loader", "plugins/ klasoru dinamik yukleyici", "system", "[PL]"),
    )),
)


def _iter_routes():
    for group, rows in FEATURE_GROUPS:
        for row in rows:
            item = _with_menu_mode(row)
            item["group"] = group
            yield item


def _manifest_payload() -> dict:
    routes = list(_iter_routes())
    groups = []
    for group, rows in FEATURE_GROUPS:
        groups.append({
            "name": group,
            "routes": [_with_menu_mode(r) for r in rows],
        })
    return {
        "version": MANIFEST_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "surfaces": list(SURFACES),
        "desktop_modes": list(DESKTOP_MODES),
        "menu_modes": list(MENU_MODES),
        "categories": deepcopy(list(MENU_CATEGORIES)),
        "groups": groups,
        "routes": routes,
        "route_count": len(routes),
        "simple_route_count": len([r for r in routes if r.get("simple")]),
        "patient_route_count": len([r for r in routes if r.get("patient_required")]),
    }


def manifest_hash(payload: dict | None = None) -> str:
    payload = deepcopy(payload or _manifest_payload())
    payload.pop("updated_at", None)
    payload.pop("hash", None)
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def get_feature_manifest() -> dict:
    payload = _manifest_payload()
    payload["hash"] = manifest_hash(payload)
    payload["ok"] = True
    return payload


def desktop_menu_categories() -> list[tuple[str, str]]:
    return [(row["key"], row["label"]) for row in MENU_CATEGORIES]


def desktop_route_groups() -> list[tuple[str, list[tuple[str, str, str]]]]:
    groups: list[tuple[str, list[tuple[str, str, str]]]] = []
    for group, rows in FEATURE_GROUPS:
        items = [
            (row["route"], row["label"], row["hint"])
            for row in rows
            if "desktop_hybrid" in row.get("surfaces", ())
        ]
        if items:
            groups.append((group, items))
    return groups


def simple_control_routes() -> set[str]:
    return {
        row["route"]
        for row in _iter_routes()
        if row.get("simple") and "desktop_hybrid" in row.get("surfaces", ())
    }


def doctor_control_routes() -> set[str]:
    return {
        row["route"]
        for row in _iter_routes()
        if row.get("doctor") and "desktop_hybrid" in row.get("surfaces", ())
    }


def webshell_nav_groups(mode: str = "advanced") -> list[tuple[str, list[tuple[str, str, str]]]]:
    mode = _normalize_menu_mode(mode)
    groups: list[tuple[str, list[tuple[str, str, str]]]] = []
    for group, rows in FEATURE_GROUPS:
        items = [
            (row["route"], row["label"], row.get("icon") or "[*]")
            for row in rows
            if "webshell" in row.get("surfaces", ())
            and _route_visible_in_menu_mode(row, mode)
        ]
        if items:
            groups.append((group, items))
    return groups


def find_route(route: str) -> dict | None:
    route = (route or "").split("?", 1)[0].rstrip("/") or "/"
    for row in _iter_routes():
        candidate = str(row.get("route") or "").split("?", 1)[0].rstrip("/") or "/"
        if candidate == route:
            return row
    return None


def route_category(route: str) -> str:
    row = find_route(route)
    if row:
        return str(row.get("category") or "today")
    return ""


def sync_status() -> dict:
    manifest = get_feature_manifest()
    route_count = int(manifest.get("route_count") or 0)
    webshell_count = len([
        r for r in manifest.get("routes", [])
        if "webshell" in r.get("surfaces", [])
    ])
    desktop_count = len([
        r for r in manifest.get("routes", [])
        if "desktop_hybrid" in r.get("surfaces", [])
    ])
    return {
        "ok": True,
        "version": manifest["version"],
        "hash": manifest["hash"],
        "route_count": route_count,
        "desktop_route_count": desktop_count,
        "webshell_route_count": webshell_count,
        "patient_route_count": manifest.get("patient_route_count", 0),
        "surfaces": manifest["surfaces"],
        "desktop_modes": manifest["desktop_modes"],
        "message": (
            "Web, hibrit masaustu ve WebShell ayni ozellik manifestini kullaniyor."
        ),
    }

