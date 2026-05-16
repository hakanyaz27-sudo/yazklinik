"""WebShell navigation routes."""

from __future__ import annotations

import sys
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

try:
    from yazklinik_textfix import fix_mojibake_text as _fix_mojibake_text
except Exception:
    def _fix_mojibake_text(value):
        return str(value or "")

NAV_GROUPS = [
    ("ANA", [
        ("/", "Ana", "[A]"),
        ("/dashboard", "Panel", "[P]"),
        ("/komuta-merkezi", "Komuta Merkezi", "[K]"),
        ("/akilli-dialog", "Akıllı Diyalog", "[D]"),
        ("/gun-plani", "Gun Plani", "[G]"),
        ("/gunluk-ozet", "Gunluk Ozet", "[O]"),
        ("/aylik-rapor", "Aylik Rapor", "[R]"),
        ("/istatistikler", "Istatistikler", "[I]"),
    ]),
    ("HASTA", [
        ("/yeni-hasta", "Yeni Hasta", "+"),
        ("/arama", "Arama", "?"),
        ("/gelismis-arama", "Gelismis Arama", "??"),
        ("/jinekoloji", "Jinekoloji", "[J]"),
        ("/obstetrik", "Obstetrik", "[O]"),
        ("/riskli-gebelik", "Riskli Gebelik Takip Merkezi", "[R]"),
        ("/medikal-estetik", "Medikal Estetik", "[M]"),
        ("/doguranlar", "Doguranlar", "[D]"),
        ("/yaklasan-dogumlar", "Yaklasan Dogumlar", "[Y]"),
        ("/karsilastir", "Karsilastir", "<>"),
    ]),
    ("MUAYENE", [
        ("/hizli-not", "Hizli Not", "[N]"),
        ("/randevular", "Randevular", "[R]"),
        ("/takvim", "Takvim", "[T]"),
        ("/randevu/yeni", "Yeni Randevu", "+"),
        ("/toplu-hatirlatma", "Toplu Hatirlatma", "[H]"),
    ]),
    ("USG / GORUNTU", [
        ("/dicom", "DICOM", "[D]"),
        ("/dicom?mode=ai", "DICOM / USG Zeka", "[DZ]"),
        ("/dicom-servisleri", "DICOM Servisleri", "[S]"),
        ("/dicom-alisveris", "DICOM Alisveris", "[X]"),
        ("/dicom-worklist", "DICOM Worklist", "[W]"),
        ("/dicom-ayar", "DICOM Ayar", "[A]"),
        ("/takip-medya-arsivi", "Takip Medya", "[M]"),
        ("/ekran-yakala", "Ekran Yakala", "[E]"),
        ("/entegrasyonlar/usg-nas", "USG NAS", "[N]"),
    ]),
    ("YZ", [
        ("/yz-asistan", "YZ Asistan", "[Y]"),
        ("/yz-sihirbazi", "YZ Sihirbazi", "[S]"),
        ("/yz-server-durum", "YZ Server", "[D]"),
        ("/yz-tahlil-yorumla", "Tahlil Yorum", "[T]"),
        ("/yz-ses-cevir", "Ses Çevir", "[S]"),
        ("/yz-telefon-diyalog", "Telefon Diyalog", "[T]"),
        ("/entegrasyon/yz-telesekreter", "YZ Telesekreter", "[AI]"),
    ]),
    ("ARACLAR", [
        ("/araclar", "Tum Araclar", "[A]"),
        ("/araclar/bmi-hesapla", "BMI", "[B]"),
        ("/araclar/gebelik-hesapla", "Gebelik", "[G]"),
        ("/araclar/fetal-tartim", "Fetal Tartim", "[F]"),
        ("/araclar/bishop-skoru", "Bishop", "[B]"),
        ("/araclar/preeklampsi-risk", "Preeklampsi", "[P]"),
        ("/araclar/ilac-rehberi", "Ilac Rehberi", "[I]"),
        ("/araclar/karar-agaci", "Karar Agaci", "[K]"),
        ("/dogum-geri-sayim", "Dogum Geri Sayim", "[D]"),
    ]),
    ("GOREVLER", [
        ("/gorevler", "Gorevler", "[G]"),
        ("/gorev/yeni", "Yeni Gorev", "+"),
        ("/akilli-bildirimler", "Akıllı Bildirim", "[B]"),
        ("/akilli-rehber", "Akıllı Rehber", "[R]"),
    ]),
    ("SABLONLAR", [
        ("/onam-sablonlari", "Onam Sablon", "[O]"),
        ("/recete-sablonlari", "Reçete Şablonu", "[R]"),
        ("/wa-sablonlar", "WhatsApp Sablon", "[W]"),
    ]),
    ("ENTEGRASYON", [
        ("/bulutklinik-aktarim", "Bulutklinik", "[B]"),
        ("/entegrasyonlar", "Entegrasyonlar", "[E]"),
        ("/entegrasyon/ip-cihazlar", "IP Cihazlar", "[IP]"),
        ("/nas-senkronizasyon", "NAS Senkron", "[N]"),
        ("/whatsapp-ayarlari", "WhatsApp Ayar", "[W]"),
        ("/wa-toplu", "WA Toplu", "[WT]"),
        ("/telefon-ara", "Telefon Ara", "[T]"),
    ]),
    ("YONETIM", [
        ("/ayarlar", "Ayarlar", "[A]"),
        ("/tum-ayarlar", "Tum Ayarlar", "[T]"),
        ("/ayar-editoru", "Ayar Editor", "[E]"),
        ("/sistem-parametreleri", "Sistem Param", "[S]"),
        ("/yazici-ayarlari", "Yazici Ayar", "[P]"),
        ("/sistem-durumu", "Sistem Durumu", "[D]"),
        ("/performans-ayarlari", "Performans", "[P]"),
        ("/protokol-ayarlari", "Protokol", "[P]"),
        ("/veri-konumlari", "Veri Konumlari", "[V]"),
        ("/veritabani-saglik-kontrol", "DB Saglik", "[DB]"),
        ("/sistem-cache-temizle", "Cache Temizle", "[C]"),
        ("/audit-log", "Audit Log", "[L]"),
    ]),
    ("YEDEK", [
        ("/otomatik-yedekler", "Yedekler", "[Y]"),
        ("/otomatik-yedek/simdi-al", "Simdi Yedek", "[S]"),
        ("/sistem-format", "Format", "[F]"),
        ("/sistem-guncelleme", "Guncelleme", "[G]"),
        ("/sistem-sifirla", "Sifirla", "[0]"),
    ]),
    ("EXPORT", [
        ("/export/hastalar.csv", "Hastalar CSV", "[CSV]"),
        ("/export/randevular.csv", "Randevular CSV", "[CSV]"),
    ]),
    ("KULLANICI", [
        ("/kullanici-ekle", "Kullanici Ekle", "[K]"),
        ("/sifre-degistir", "Sifre Degistir", "[S]"),
        ("/yardim", "Yardim", "?"),
        ("/cikis", "Cikis", "[X]"),
    ]),
]

def _normalize_menu_mode(mode: str) -> str:
    mode = str(mode or "").strip().lower()
    if mode in {"simple", "basit"}:
        return "simple"
    if mode in {"doctor", "doktor"}:
        return "doctor"
    if mode in {"advanced", "expert", "uzman"}:
        return "advanced"
    return "advanced"


try:
    from yazklinik_feature_sync import webshell_nav_groups as _sync_webshell_nav_groups
except Exception:
    _sync_webshell_nav_groups = None


def nav_groups_for_mode(mode: str = "advanced"):
    if _sync_webshell_nav_groups is not None:
        try:
            groups = _sync_webshell_nav_groups(_normalize_menu_mode(mode))
        except TypeError:
            groups = _sync_webshell_nav_groups()
        except Exception:
            groups = []
        if groups:
            cleaned: list[tuple[str, list[tuple[str, str, str]]]] = []
            for cat, items in groups:
                cat_text = _fix_mojibake_text(str(cat or ""))
                rows: list[tuple[str, str, str]] = []
                for route, label, icon in items:
                    route_text = str(route or "")
                    label_text = _fix_mojibake_text(str(label or route_text or "/"))
                    icon_text = str(icon or "[*]")
                    rows.append((route_text, label_text, icon_text))
                if rows:
                    cleaned.append((cat_text, rows))
            if cleaned:
                return cleaned
    return NAV_GROUPS


try:
    _SYNC_NAV_GROUPS = nav_groups_for_mode("advanced")
    if _SYNC_NAV_GROUPS:
        NAV_GROUPS = _SYNC_NAV_GROUPS
except Exception:
    pass


def all_routes(mode: str = "advanced"):
    out = []
    for cat, items in nav_groups_for_mode(mode):
        for route, label, icon in items:
            out.append((route, label, icon, cat))
    return out
