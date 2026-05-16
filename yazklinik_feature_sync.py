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


MANIFEST_VERSION = "2026.05.16-D300-AGENTS-IG"

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
}


def _route_menu_mode(row: dict) -> str:
    route = str(row.get("route") or "")
    if route in SIMPLE_ROUTINE_ROUTES:
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
        _r("/", "Hastalar", "Hasta listesi ve arama", "patient", "[A]", simple=True),
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
        _r("/hasta/{patient}", "Hasta Özeti", "Seçili hasta kartı", "patient", "[H]", webshell=False, simple=True),
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
        _r("/karsilastir", "Karsilastir", "Hasta/olcum karsilastirma", "clinical", "<>"),
    )),
    ("MUAYENE", (
        _r("/hizli-not", "Hizli Not", "Aninda not", "today", "[N]", simple=True),
        _r("/randevular", "Randevular", "Liste gorunumu", "today", "[R]", simple=True),
        _r("/takvim", "Takvim", "Takvim gorunumu", "today", "[T]", simple=True),
        _r("/randevu/yeni", "Yeni Randevu", "Yeni randevu olustur", "today", "+"),
        _r("/toplu-hatirlatma", "Toplu Hatirlatma", "Randevu hatirlatmalari", "today", "[H]"),
        _r("/gorevler", "Gorevler", "Is listesi", "today", "[G]", simple=True),
        _r("/gorev/yeni", "Yeni Gorev", "Yeni gorev olustur", "today", "+"),
        _r("/akilli-bildirimler", "Akıllı Bildirim", "Sistemin tespit ettiği uyarılar", "today", "[B]", simple=True),
    )),
    ("KLINIK", (
        _r("/hasta/{patient}/gebelik-takip-plani", "Gebelik Takip", "A4 tarihli takip formu", "clinical", "[GT]", webshell=False),
        _r("/hasta/{patient}/gebelik-gelisim-takibi", "Gebelik Gelisim", "PDF USG buyume grafikleri", "clinical", "[GG]", webshell=False),
        _r("/hasta/{patient}/tahliller", "Tahliller", "Hasta tahlil dosyalari", "clinical", "[T]", webshell=False),
        _r("/hasta/{patient}/tetkik-istemi", "Tetkik Istemi", "Tetkik istem formu", "clinical", "[TI]", webshell=False),
        _r("/hasta/{patient}/recete-hazirla", "Reçete", "2 harften ilaç/tanı bulan reçete ekranı", "clinical", "[RX]", webshell=False),
        _r("/hasta/{patient}/sesli-recete", "Sesli Reçete", "Seçili hastaya sesli reçete", "ai", "[SR]", webshell=False),
        _r("/hasta/{patient}/konusarak-not", "Konuşarak Not", "Mikrofonla hasta notu", "ai", "[KN]", webshell=False),
        _r("/hasta/{patient}/yz-recete-oner", "YZ Reçete", "Reçete öneri kontrolü", "ai", "[YR]", webshell=False),
        _r("/hasta/{patient}/yz-diyet", "Diyet", "Hasta diyet listesi", "clinical", "[DY]", webshell=False),
        _r("/onam-sablonlari", "Onam Sablonlari", "Database onam kutuphanesi", "clinical", "[O]", simple=True),
        _r("/recete-sablonlari", "Hazır Reçeteler", "Database reçete kütüphanesi", "clinical", "[R]", simple=True),
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
        _r("/pelvik-enfeksiyon", "Pelvik Enfeksiyon & Vajinit", "Akıntı rengi -> tanı + 8 mixt enfeksiyon protokolü", "clinical", "[PID]", simple=True, aliases=("vajinit", "pid")),
        _r("/ilac-guvenlik", "Ilac Guvenligi", "Gebelikte ilac kategori + ilac-ilac etkilesim + protokoler", "clinical", "[GUV]", simple=True, aliases=("recete kontrol", "gebelikte ilac")),
        _r("/tedavi-planla", "Tedavi Planlayıcı (Super)", "Hasta autocomplete + protokol + DDI etkileşim + A5 reçete + QR + PDF", "clinical", "[RX+]", simple=True, aliases=("recete yardimcisi", "ilac onerisi", "tedavi onerisi", "tedavi super", "rx super")),
        _r("/hasta-birlestir", "Hasta Birlestir (Merge)", "Iki hasta ayni kisiyse tek hastaya birlestir - tum visits/PDF/USG/recete tasinir, source arsivlenir", "patient", "[MRG]", aliases=("hasta merge", "birlestir", "ayni hasta", "tek hasta")),
        _r("/sistem-ayarlari", "Sistem Ayarları (D250)", "NAS yolu (\\\\asustor\\Voluson), lokal DB, port - config.env editleyici", "system", "[CFG]", aliases=("ayar", "config", "nas degistir", "db path", "yk-ayarlar")),
        _r("/gebelik-komplikasyon", "Gebelik Komplikasyon", "Hiperemezis/abortus/ektopik/mol/PPH/HELLP acil yonetim", "clinical", "[KMP]", aliases=("obstetrik acil",)),
    )),
    ("USG_GORUNTU", (
        _r("/dicom", "DICOM/PACS", "Orthanc ve görüntü", "media", "[D]", simple=True),
        _r("/dicom?mode=ai", "DICOM / USG Zeka", "Orthanc, viewer, olcum ve AI merkezi", "media", "[DZ]", simple=True, aliases=("dicom ai", "usg zeka", "orthanc ai")),
        _r("/dicom-servisleri", "DICOM Servisleri", "Orthanc plugin merkezi", "media", "[S]", simple=True),
        _r("/dicom-alisveris", "DICOM Alisveris", "Voluson Worklist, C-STORE ve C-ECHO akisi", "media", "[X]", simple=True, aliases=("voluson", "worklist", "pacs alisveris")),
        _r("/dicom-worklist", "DICOM Worklist", "DICOM is listesi", "media", "[W]"),
        _r("/dicom-ayar", "DICOM Ayar", "Orthanc ve PACS parametreleri", "system", "[A]"),
        _r("/kamera", "Kamera / NVR", "Ic ag NVR panelini 5443 uzerinden proxy ile izle", "media", "bi bi-camera-video", simple=True, aliases=("kamera", "nvr", "ip kamera", "guvenlik kamera")),
        _r("/hd-studio", "HD Studio", "Seçili hastanın HD Live USG resim/video iyileştirme ekranı", "media", "[HD]", simple=True, aliases=("hd studio", "usg", "mp4", "video")),
        _r("/bebek-goruntu-zeka", "Bebek YZ", "Lokal bebek/USG anomali ön tarama ve kalite artırma", "media", "[BZ]", simple=True, aliases=("bebek", "anomali", "kalite", "fetal")),
        _r("/takip-medya-arsivi", "Medya Arsivi", "Oncesi/sonrasi medya", "media", "[M]", simple=True),
        _r("/hasta/{patient}/takip-medya", "Medya", "Hasta medya takibi", "media", "[M]", webshell=False),
        _r("/hasta/{patient}/takip-medya?module=medical_aesthetic", "Medikal Estetik Medya", "Estetik medya akisi", "media", "[ME]", webshell=False),
        _r("/hasta/{patient}/dosya-gezgini", "NAS/DICOM Gezgin", "Hasta klasoru ve DICOM gezgini", "media", "[N]", webshell=False),
        _r("/hasta/{patient}/dicom-medya", "DICOM Medya", "Hasta DICOM medya", "media", "[DM]", webshell=False),
        _r("/hasta/{patient}/dicom", "DICOM / USG Zeka", "Orthanc eslestirme, OCR olcum ve AI on inceleme", "media", "[DZ]", webshell=False, simple=True, aliases=("usg zeka", "dicom zeka", "orthanc ai", "olcum")),
        _r("/dicom?patient={patient}", "Hasta DICOM/PACS", "Seçili hastanın DICOM görüntüsü", "media", "[P]", webshell=False),
        _r("/hasta/{patient}/yz-resim-iyilestir", "HD Studio", "HD Live USG resim/video iyilestirme", "media", "[HD]", webshell=False, simple=True, aliases=("usg", "mp4", "video")),
        _r("/hasta/{patient}/pdf-editor", "PDF Rapor Editoru", "Rapor duzenleme", "media", "[PDF]", webshell=False),
        _r("/hasta/{patient}/pdf-atolyesi", "PDF Atolyesi", "Program ici PDF islemleri", "media", "[PA]", webshell=False),
        _r("/hasta/{patient}/rapor-pdf-yazdir", "PDF Yazdir", "Son PDF raporu yazdir", "media", "[PY]", webshell=False),
        _r("/ekran-yakala", "Ekran Yakala", "OCR + YZ", "media", "[E]", simple=True),
        _r("/entegrasyonlar/usg-nas", "USG NAS", "USG/NAS aktarım ayarları", "media", "[N]"),
    )),
    ("YZ Asistanlar", (
        _r("/yz-asistan", "YZ Asistan", "Klinik asistan", "ai", "bi bi-robot", simple=True),
        _r("/akilli-rehber", "Akıllı Rehber", "Yol gösterici asistan", "ai", "bi bi-compass", simple=True),
        _r("/yz-komut-merkezi", "YZ Komut", "Sesli/yazılı komut merkezi", "ai", "bi bi-terminal", simple=True),
        _r("/hasta/{patient}/akilli-asistan", "Hasta Akıllı Asistan", "Hafıza, not, reçete ve risk özeti", "ai", "bi bi-person-vcard", webshell=False),
        _r("/hasta/{patient}/hafiza", "Hasta Hafızası", "Alerji, risk ve önemli not kartları", "ai", "bi bi-journal-medical", webshell=False),
    )),
    ("Ses ve Akıllı Diyalog", (
        _r("/ses-ve-alex", "Ses ve Alex Merkezi", "Akıllı Diyalog, sesli görüşme ve ses ayarları tek yerde", "ai", "bi bi-mic-fill", simple=True, aliases=("ses merkezi", "alex ses", "akilli dialog ses")),
        _r("/akilli-dialog", "Akıllı Diyalog", "ChatGPT gibi konuşan ve iş yapan ajan", "ai", "bi bi-chat-dots", simple=True),
        _r("/sessiz-alex", "Sessiz Alex", "Klavye ile sessiz Akıllı Diyalog", "ai", "bi bi-keyboard", simple=True, aliases=("sessiz dialog", "klavye alex", "yazarak alex")),
        _r("/bilgi-ajanlari", "Bilgi Ajanları", "PubMed + güvenilir web bilgisini kaynaklı YAZ hafızasına işler", "ai", "bi bi-broadcast", simple=True, aliases=("yaz llm", "webden ogren", "webden öğren", "kaynakli bilgi", "kaynaklı bilgi", "bilgi ajanlari")),
        _r("/alex-arastirma", "Alex Araştırma", "PubMed + web online arama, Türkçe özet + klinik öneri", "ai", "bi bi-search-heart", simple=True, aliases=("pubmed", "literatur tara", "online arastir", "alex arastirma", "tibbi arastirma")),
        _r("/alex-egitim", "Alex Eğitim", "Alex'e kalıcı bilgi öğret + özel komut (Windows aksiyon) tanımla", "ai", "bi bi-mortarboard-fill", simple=True, aliases=("alex egit", "ogret", "hafiza yonet", "komut tanimla")),
        _r("/sesli-recete", "Sesli Reçete", "Konuşarak reçete taslağı", "ai", "bi bi-mic", simple=True),
        _r("/hizmet-ajanlari", "Hizmet Ajanları", "Randevu, hasta takip, reçete, BK-Voluson ve Alex ajanları", "ai", "bi bi-person-workspace", simple=True, aliases=("benim ajanlarim", "ajanlarim", "hizmet eden ajanlar", "calisan ajanlar")),
        _r("/yz-ses-cevir", "Ses Çevir", "Sesli notu metne çevir", "ai", "bi bi-soundwave"),
        _r("/ses-profilleri", "Alex Ses Seçimi", "Alex konuşma sesi ve ses profilleri", "ai", "bi bi-volume-up", simple=True, aliases=("ses profilleri", "alex sesi", "tts")),
        _r("/mikrofon-tani", "Mikrofon Tanı", "Mikrofon ve ses sistemi testi", "ai", "bi bi-mic-mute", simple=True, aliases=("mikrofon", "ses testi")),
        _r("/yz-telefon-diyalog", "Telefon Diyalog", "Türkçe telefon sohbeti", "ai", "bi bi-telephone", simple=True),
        _r("/entegrasyon/yz-telesekreter", "YZ Telesekreter", "IP telefon/PBX", "ai", "bi bi-telephone-inbound", simple=True),
    )),
    ("YZ Analiz ve Otomasyon", (
        _r("/yz-tahlil-yorumla", "Tahlil Yorum", "Tahlil yorumlama", "ai", "bi bi-clipboard2-pulse"),
        _r("/islem-zincirleri", "İşlem Zincirleri", "Reçete, randevu ve WhatsApp taslakları", "ai", "bi bi-diagram-3", simple=True),
        _r("/gun-sonu-ozeti", "Gün Sonu Özeti", "Günlük klinik özet", "ai", "bi bi-moon-stars", simple=True),
        _r("/hasta/{patient}/gorsel-tani-destegi", "Resimle Ön Tanı", "Hasta resmiyle ön tanı ve ilaç ön önerisi", "ai", "bi bi-image", webshell=False),
        _r("/hasta/{patient}/yz-anomali-tarama", "YZ Anomali", "USG anomali ön tarama", "ai", "bi bi-bounding-box", webshell=False),
        _r("/hasta/{patient}/yz-medya-analiz", "YZ Medya", "Hasta medya analizi", "ai", "bi bi-images", webshell=False),
    )),
    ("YZ Ayarlar", (
        _r("/online-chatgpt", "Online ChatGPT", "OpenAI + Ollama ayarları", "ai", "bi bi-cloud-check", simple=True),
        _r("/yz-sihirbazi", "YZ Sihirbazı", "Model ve ayar yardımcısı", "ai", "bi bi-magic", simple=True),
        _r("/yz-kurulum-rehberi", "YZ Kurulum", "YZ kurulum rehberi", "ai", "bi bi-rocket-takeoff"),
        _r("/yz-server-durum", "YZ Server", "Ollama durumu", "ai", "bi bi-hdd-network", simple=True),
    )),
    ("SABLONLAR", (
        _r("/wa-sablonlar", "WhatsApp Sablon", "WhatsApp mesaj sablonlari", "patient", "[W]"),
        _r("/hasta/{patient}/whatsapp", "WhatsApp", "Hasta WhatsApp mesaji", "patient", "[WA]", webshell=False),
        _r("/hasta/{patient}/onam", "Onam", "Hasta onam akisi", "clinical", "[ON]", webshell=False),
        _r("/onam-sablonlari?patient={patient}", "Hasta Onam Şablonu", "Seçili hasta onam şablonu", "clinical", "[OS]", webshell=False),
        _r("/recete-sablonlari?patient={patient}", "Hasta Reçete Şablonu", "Seçili hasta hazır reçete", "clinical", "[RS]", webshell=False),
    )),
    ("ENTEGRASYON", (
        _r("/bulutklinik", "BulutKlinik Ajani", "BulutKlinik resmi API connector", "system", "[BK]", simple=True, aliases=("bulutklinik", "cloud klinik")),
        _r("/enabiz", "e-Nabiz Ajani", "e-Nabiz hasta paylasimli PDF aktarim", "system", "[EN]", simple=True, aliases=("e-nabiz", "enabiz", "saglik bakanligi")),
        _r("/bulutklinik-aktarim", "Bulutklinik (eski)", "Eski bulutklinik aktarim sayfasi", "system", "[B]"),
        _r("/entegrasyon-ajanlari", "YZ Entegrasyon Ajanlari", "BulutKlinik, e-Nabiz, DoktorTakvimi ve KVKK ajanlari", "system", "[AI]", simple=True, aliases=("bulutklinik", "enabiz", "doktor takvimi", "dis entegrasyon")),
        _r("/entegrasyonlar", "Entegrasyonlar", "Tum entegrasyonlar", "system", "[E]"),
        _r("/entegrasyon/ip-cihazlar", "IP Cihazlar", "IP kamera/telefon/PBX", "system", "[IP]"),
        _r("/nas-senkronizasyon", "NAS Senkron", "NAS surucu senkronizasyonu", "system", "[N]"),
        _r("/whatsapp-ayarlari", "WhatsApp Ayar", "WhatsApp ayarları", "system", "[W]"),
        _r("/wa-toplu", "WA Toplu", "Toplu WhatsApp islemleri", "patient", "[WT]"),
        _r("/telefon-ara", "Telefon Ara", "Telefon arama kisayolu", "patient", "[T]"),
        _r("/sohbet-merkezi", "Sohbet Merkezi", "Sohbet ve randevu talepleri", "patient", "[SOH]", simple=True),
        _r("/randevu-onay", "Randevu Onay", "YZ randevu taleplerini onayla", "patient", "[RO]", simple=True),
    )),
    ("SISTEM", (
        _r("/terminal-cihaz-merkezi", "Terminal/Cihaz", "Terminal, iPhone, Mac, medya ve WhatsApp istemci modu", "system", "bi bi-phone", simple=True, aliases=("terminal", "cihaz", "iphone", "mac", "whatsapp cihaz", "resim cihaz")),
        _r("/ozellik-senkron", "Hibrit/Web Senkron", "Ortak ozellik manifesti ve menu senkronizasyonu", "system", "[SYNC]", simple=True, aliases=("senkron", "sync")),
        _r("/sistem-durumu", "Sistem Durumu", "Server, YZ, DICOM ve depolama durumu", "system", "[D]", simple=True),
        _r("/sistem-durumu-ozet", "Sistem Ozet", "Terminal uyumlu sistem ozeti", "system", "[O]"),
        _r("/ayarlar", "Ayarlar", "Web ayarları", "system", "[A]", simple=True),
        _r("/performans-ayarlari", "Performans", "RAM ve masaustu hiz modu", "system", "[P]", simple=True),
        _r("/sistem/dosya-konumlari", "Dosya Konumlari", "NAS, medya, cikti ve yedek yollari", "system", "[V]", simple=True),
        _r("/veri-konumlari", "Veri Konumlari", "Sistem dosya haritasi", "system", "[V]"),
        _r("/tum-ayarlar", "Tum Ayarlar", "Butun kontrol anahtarlari", "system", "[T]"),
        _r("/ayar-editoru", "Ayar Editor", "Uzman ayar editoru", "system", "[E]"),
        _r("/sistem-parametreleri", "Sistem Param", "YZ modelleri, port ve timeout", "system", "[S]"),
        _r("/yazici-ayarlari", "Yazıcı Ayar", "Yazıcı ve çıktı ayarları", "system", "[P]"),
        _r("/protokol-ayarlari", "Protokol", "Protokol ayarları", "system", "[P]"),
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
    ("AJANLAR", (
        _r("/ajanlar", "Klinik Ajanlari", "11 ajan dashboard + manifest", "ai", "[AJ]",
           simple=True, aliases=("agents", "ajan paneli", "ajan merkezi")),
        _r("/instagram-hazirla", "Instagram Hazirla", "USG arsivinden Instagram draft (KVKK)", "ai", "[IG]",
           simple=True, aliases=("instagram", "ig", "sosyal medya", "post hazirla")),
        _r("/api/agents/telesekreter/run", "YZ Telesekreter", "Aramayi triyaj eder", "ai", "[TS]"),
        _r("/api/agents/sesli_onay/run", "Sesli Randevu Onay", "Evet/hayir/ertele karari", "ai", "[SO]"),
        _r("/api/agents/usg_rapor/run", "USG Rapor Taslak", "Olcumden EFW+rapor", "ai", "[UR]"),
        _r("/api/agents/geri_cagirma/run", "Geri Cagirma", "Hatirlatma kuyrugu", "ai", "[GC]"),
        _r("/api/agents/bk_sync_bekci/run", "BK Sync Bekci", "BulutKlinik baglanti saglik", "ai", "[BS]"),
        _r("/api/agents/nas_yedek_izleyici/run", "NAS Yedek Izleyici", "Yedek+disk saglik", "ai", "[NY]"),
        _r("/api/agents/recete_hazirlayici/run", "Recete Taslak", "Gecmis+alerji ile recete", "ai", "[RT]"),
        _r("/api/agents/gunluk_ozet/run", "Gunluk Ozet", "Gun sonu klinik ozeti", "ai", "[GO]"),
        _r("/api/agents/mojibake_bekci/run", "Mojibake Bekci", "Encoding tespit (read-only)", "system", "[MB]"),
        _r("/api/agents/pr_reviewer/run", "PR Reviewer", "Diff sablon kontrol", "system", "[PR]"),
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
