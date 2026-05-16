"""BulutKlinik CSV -> YazKlinik SQLite import.

Tablolar:
  bk_patients   : BulutKlinik hasta tablosunun tam kopyasi (TC pk olarak)
  bk_protocols  : BulutKlinik protokol tablosu (Protokol No pk)

Akis:
  1) cookie client ile Hastalar.csv + Protokoller.csv indir
  2) Tarih filtre: 'since_days' (default 90) - protokol_tarihi >= now-since_days
  3) Bu protokollerin hasta no'larini al, Hastalar.csv'den sadece o hastalari upsert
  4) Protokolleri upsert

Kullanim:
  python yazklinik_bulutklinik_import.py --since 90
  python yazklinik_bulutklinik_import.py --since 90 --dry-run
"""
from __future__ import annotations
import sys, io, os, csv, sqlite3, datetime, argparse, re, json, hashlib, unicodedata

DB_PATH = r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3"
LAST_MIRROR_STATS = None


def _safe_print(*args, **kwargs):
    """Module reload sonrasi stdout kapali olabilir; sessiz dus.
    builtins.print kullanir ki replace_all bug'lari recursion'a yol acmasin."""
    import builtins as _b
    try:
        _b.print(*args, **kwargs)
    except (ValueError, OSError):
        pass


# CLI disindan import edildiginde print() yerine _safe_print kullan
# (Flask reload sonrasi 'I/O operation on closed file' icin guvence).
# CLI'da normal print, modul olarak ise safe wrapper.
def _is_cli():
    return __name__ == "__main__"

# === Schema ===

SCHEMA = """
CREATE TABLE IF NOT EXISTS bk_obstetri_index (
    bk_hasta_no   TEXT PRIMARY KEY,
    visit_count   INTEGER DEFAULT 0,
    last_visit    TEXT,
    first_visit   TEXT,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bk_obs_last ON bk_obstetri_index(last_visit);

CREATE TABLE IF NOT EXISTS bk_obstetri_visits (
    bk_hasta_no   TEXT NOT NULL,
    takip_no      TEXT,
    tarih         TEXT,
    usg_age       TEXT,
    efw           TEXT,
    amnion        TEXT,
    plasenta      TEXT,
    serviks       TEXT,
    hb            TEXT,
    hct           TEXT,
    mcv           TEXT,
    plt           TEXT,
    tit           TEXT,
    diger         TEXT,
    kilo          TEXT,
    ta            TEXT,
    sikayet       TEXT,
    olusturulma   TEXT,
    guncelleme    TEXT,
    row_hash      TEXT PRIMARY KEY
);
CREATE INDEX IF NOT EXISTS idx_bk_obs_visits_hasta
    ON bk_obstetri_visits(bk_hasta_no, tarih);

CREATE TABLE IF NOT EXISTS bk_payments (
    payment_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    protokol_no   TEXT,
    bk_hasta_no   TEXT,
    hasta_ad      TEXT,
    hasta_soyad   TEXT,
    odenen        TEXT,
    cinsi         TEXT,
    tarih         TEXT,
    row_hash      TEXT UNIQUE,
    imported_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bk_pay_hasta ON bk_payments(bk_hasta_no);
CREATE INDEX IF NOT EXISTS idx_bk_pay_protokol ON bk_payments(protokol_no);

CREATE TABLE IF NOT EXISTS bk_patients (
    bk_hasta_no       TEXT PRIMARY KEY,   -- BulutKlinik Hasta No
    tc_kimlik         TEXT,
    ad                TEXT,
    soyad             TEXT,
    cinsiyet          TEXT,
    uyruk             TEXT,
    pasaport_no       TEXT,
    gelis_tarihi      TEXT,
    ozgecmis          TEXT,
    soygecmis         TEXT,
    alerjiler         TEXT,
    gelis_nedeni      TEXT,
    adres             TEXT,
    dogum_tarihi      TEXT,
    dogum_yeri        TEXT,
    telefon           TEXT,
    eposta            TEXT,
    kan_grubu         TEXT,
    baba_adi          TEXT,
    anne_adi          TEXT,
    medeni_hali       TEXT,
    not_text          TEXT,
    anlasmali_kurum   TEXT,
    imported_at       TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bk_patients_tc ON bk_patients(tc_kimlik);
CREATE INDEX IF NOT EXISTS idx_bk_patients_ad_soyad ON bk_patients(ad, soyad);

CREATE TABLE IF NOT EXISTS bk_protocols (
    protokol_no       TEXT PRIMARY KEY,
    bk_hasta_no       TEXT,
    isim              TEXT,
    soyisim           TEXT,
    baba_adi          TEXT,
    anne_adi          TEXT,
    anne_tc_no        TEXT,
    anlasmali_kurum   TEXT,
    brans             TEXT,
    doktor            TEXT,
    protokol_tarihi   TEXT,  -- ISO datetime
    protokol_tipi     TEXT,
    gelis_nedeni      TEXT,
    imported_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bk_protocols_hasta ON bk_protocols(bk_hasta_no);
CREATE INDEX IF NOT EXISTS idx_bk_protocols_tarih ON bk_protocols(protokol_tarihi);

CREATE TABLE IF NOT EXISTS bk_medical_infos (
    protokol_no       TEXT PRIMARY KEY,
    bk_hasta_no       TEXT,
    hasta_tc          TEXT,
    hasta_ad          TEXT,
    hasta_soyad       TEXT,
    protokol_tarihi   TEXT,
    hikayesi          TEXT,
    sikayeti          TEXT,
    ozgecmis          TEXT,
    soygecmis         TEXT,
    bulgular          TEXT,
    uygulamalar       TEXT,
    oneriler          TEXT,
    notlar            TEXT,
    tani_kodlari      TEXT,
    imported_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bk_medical_hasta ON bk_medical_infos(bk_hasta_no);

CREATE TABLE IF NOT EXISTS bk_services (
    row_hash          TEXT PRIMARY KEY,
    protokol_no       TEXT,
    bk_hasta_no       TEXT,
    hizmet_no         TEXT,
    hasta_ad          TEXT,
    islem_tarihi      TEXT,
    hizmet_adi        TEXT,
    grup_adi          TEXT,
    adet              TEXT,
    hasta_tutari      TEXT,
    kurum_tutari      TEXT,
    indirim_tutari    TEXT,
    tahsilat_tutari   TEXT,
    imported_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bk_services_protokol ON bk_services(protokol_no);
CREATE INDEX IF NOT EXISTS idx_bk_services_hasta ON bk_services(bk_hasta_no);

CREATE TABLE IF NOT EXISTS bk_appointments (
    row_hash          TEXT PRIMARY KEY,
    bk_hasta_no       TEXT,
    hasta_ad          TEXT,
    hasta_soyad       TEXT,
    telefon           TEXT,
    baslangic         TEXT,
    bitis             TEXT,
    randevu_tipi      TEXT,
    baslik            TEXT,
    not_text          TEXT,
    durum             TEXT,
    doktor            TEXT,
    kaynak            TEXT,
    imported_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bk_appointments_hasta ON bk_appointments(bk_hasta_no);

CREATE TABLE IF NOT EXISTS bk_gynecology_resume (
    row_hash          TEXT PRIMARY KEY,
    bk_hasta_no       TEXT,
    protokol_no       TEXT,
    resume_no         TEXT,
    tarih             TEXT,
    son_adet_tarihi   TEXT,
    sikayet_oyku      TEXT,
    bulgular          TEXT,
    notlar            TEXT,
    tani              TEXT,
    tedavi_plani      TEXT,
    recete            TEXT,
    sonuc             TEXT,
    data_json         TEXT,
    imported_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bk_gyn_resume_hasta ON bk_gynecology_resume(bk_hasta_no);
CREATE INDEX IF NOT EXISTS idx_bk_gyn_resume_protokol ON bk_gynecology_resume(protokol_no);

CREATE TABLE IF NOT EXISTS bk_gynecology_tracking (
    row_hash          TEXT PRIMARY KEY,
    bk_hasta_no       TEXT,
    resume_no         TEXT,
    takip_no          TEXT,
    tarih             TEXT,
    usg_age           TEXT,
    efw               TEXT,
    amnion            TEXT,
    plasenta          TEXT,
    serviks           TEXT,
    hb                TEXT,
    hct               TEXT,
    mcv               TEXT,
    plt               TEXT,
    tit               TEXT,
    diger             TEXT,
    kilo              TEXT,
    ta                TEXT,
    sikayet           TEXT,
    data_json         TEXT,
    imported_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bk_gyn_tracking_hasta ON bk_gynecology_tracking(bk_hasta_no, tarih);
"""


def ensure_schema(con: sqlite3.Connection) -> None:
    for stmt in SCHEMA.strip().split(";"):
        s = stmt.strip()
        if s:
            con.execute(s)
    con.commit()


def parse_date(s: str) -> datetime.datetime | None:
    if not s or not s.strip():
        return None
    s = s.strip()
    fmts = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
            "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y",
            "%d/%m/%Y", "%Y/%m/%d")
    for f in fmts:
        try:
            return datetime.datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def read_csv(path: str) -> tuple[list[str], list[list[str]]]:
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
        sample = f.read(8000)
    delim = ';' if sample.count(';') > sample.count(',') else ','
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
        rdr = csv.reader(f, delimiter=delim)
        rows = list(rdr)
    if not rows:
        return [], []
    return rows[0], rows[1:]


_TR_ASCII = str.maketrans({
    "\u00c7": "C", "\u00e7": "c",
    "\u011e": "G", "\u011f": "g",
    "\u0130": "I", "\u0131": "i",
    "\u00d6": "O", "\u00f6": "o",
    "\u015e": "S", "\u015f": "s",
    "\u00dc": "U", "\u00fc": "u",
})


def _norm_key(value) -> str:
    text = str(value or "").translate(_TR_ASCII)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text


def _read_csv_dicts(path: str) -> list[dict]:
    hdr, rows = read_csv(path)
    keys = [_norm_key(h) for h in hdr]
    out = []
    for row in rows:
        if len(row) < len(keys):
            row = row + [""] * (len(keys) - len(row))
        obj = {keys[i]: (row[i] if i < len(row) else "") for i in range(len(keys))}
        if any(str(v or "").strip() for v in obj.values()):
            out.append(obj)
    return out


def _pick(row: dict, *keys: str) -> str:
    for key in keys:
        val = row.get(_norm_key(key))
        if val not in (None, ""):
            return str(val).strip()
    return ""


def _hash_values(*parts) -> str:
    src = "|".join(str(p or "") for p in parts)
    return hashlib.md5(src.encode("utf-8", errors="replace")).hexdigest()


def _protocol_patient_lookup(con: sqlite3.Connection) -> dict[str, str]:
    try:
        return {
            str(r[0] or ""): str(r[1] or "")
            for r in con.execute(
                "SELECT protokol_no, bk_hasta_no FROM bk_protocols").fetchall()
        }
    except Exception:
        return {}


def _find_export_file(exports_dir: str, slug: str, ext: str) -> str | None:
    if not exports_dir:
        return None
    root = os.path.abspath(exports_dir)
    if not os.path.isdir(root):
        return None
    wanted = _norm_key(slug)
    ext = "." + ext.lower().lstrip(".")
    best = None
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if not os.path.isfile(path) or not name.lower().endswith(ext):
            continue
        norm = _norm_key(os.path.splitext(name)[0])
        if norm == wanted or wanted in norm or norm in wanted:
            best = path
            break
    if best:
        return best
    aliases = {
        "hizmetler": ("islenmis_hizmetler", "hizmet"),
        "tahsilatlar": ("tahsilat", "indirim"),
        "medikal": ("medikal_bilgiler", "medikal"),
        "obstetri": ("kadin_sagligi_obstetri", "obstetri"),
        "jinekoloji": ("kadin_sagligi_jinekoloji", "jinekoloji"),
        "randevular": ("randevu",),
    }
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if not os.path.isfile(path) or not name.lower().endswith(ext):
            continue
        norm = _norm_key(os.path.splitext(name)[0])
        if any(a in norm for a in aliases.get(wanted, ())):
            return path
    return None


def _existing_exports_manifest(exports_dir: str) -> dict:
    sys.path.insert(0, r"D:\YazKlinik_Final_D300")
    import yazklinik_bulutklinik_cookie_client as bkc
    out = {"ok": True, "files": {}}
    for cid, (slug, _name, ext) in bkc.BulutklinikCookieClient.EXPORT_CATEGORIES.items():
        path = _find_export_file(exports_dir, slug, ext)
        if path:
            out["files"][slug] = {"path": path, "size": os.path.getsize(path)}
    if "hastalar" not in out["files"] or "protokoller" not in out["files"]:
        return {"ok": False, "error": "exports-dir icinde hastalar/protokoller yok"}
    return out


def download_fresh(out_dir: str) -> dict:
    sys.path.insert(0, r"D:\YazKlinik_Final_D300")
    import yazklinik_bulutklinik_cookie_client as bkc
    cl = bkc.get_client()
    if not cl or not cl.check_auth():
        return {"ok": False, "error": "Cookie yok / expired"}
    os.makedirs(out_dir, exist_ok=True)
    # D300: tum klinik exportlar alinir. Hasta/protokol zorunlu;
    # hizmet, medikal, randevu, obstetri, jinekoloji opsiyoneldir.
    out = {"ok": True, "files": {}}
    for cid in sorted(cl.EXPORT_CATEGORIES.keys()):
        r = cl.export_category(cid)
        if not r.get("ok"):
            if cid not in (0, 2):
                _safe_print(f"  [UYARI] cid={cid} export fail: {r.get('error')}")
                continue
            return {"ok": False, "error": f"export({cid}) fail: {r.get('error')}"}
        slug, name, ext = cl.EXPORT_CATEGORIES[cid]
        path = os.path.join(out_dir, f"{slug}.{ext}")
        with open(path, "wb") as f:
            f.write(r["content"])
        out["files"][slug] = {"path": path, "size": r["size"]}
        _safe_print(f"  [OK] {name}: {path} ({r['size']/1024:.1f} KB)")
    return out


def import_obstetri_xlsx(con: sqlite3.Connection, path: str) -> tuple[int, int]:
    """obstetri.xlsx -> bk_obstetri_index (count) + bk_obstetri_visits (tum satir)."""
    if not os.path.exists(path):
        return 0, 0
    try:
        import openpyxl
        import hashlib
    except ImportError:
        _safe_print("  [SKIP] openpyxl yok, obstetri import atlandi")
        return 0, 0
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows or len(rows) < 2:
        return 0, 0
    hdr = list(rows[0])
    try:
        h_no = hdr.index("Hasta No")
    except ValueError:
        _safe_print(f"  [UYARI] obstetri 'Hasta No' kolonu yok: {hdr}")
        return 0, 0
    # Kolon indexleri (varsa)
    def _idx(name):
        try:
            return hdr.index(name)
        except ValueError:
            return None
    cols = {
        "takip_no": _idx("Takip Numarası"),
        "tarih": _idx("Takip Tarihi") or _idx("Tarih"),
        "usg_age": _idx("Usg Age"),
        "efw": _idx("Efw"),
        "amnion": _idx("Amnion"),
        "plasenta": _idx("Plasenta"),
        "serviks": _idx("Serviks"),
        "hb": _idx("Hb"),
        "hct": _idx("Hct"),
        "mcv": _idx("Mcv"),
        "plt": _idx("Plt"),
        "tit": _idx("Tit"),
        "diger": _idx("Diğer"),
        "kilo": _idx("Kilo") or _idx("Kio"),
        "ta": _idx("Ta"),
        "sikayet": _idx("Şikayet"),
        "olusturulma": _idx("Oluşturulma Tarihi") or _idx("OLuşturulma Tarihi"),
        "guncelleme": _idx("Güncelleme Tarihi"),
    }

    def _get(row, key):
        i = cols[key]
        if i is None or i >= len(row) or row[i] is None:
            return None
        return str(row[i]).strip() or None

    agg = {}  # bk_hasta_no -> {count, first, last}
    detail_ins = 0
    for r in rows[1:]:
        if not r or h_no >= len(r) or r[h_no] is None:
            continue
        no_str = str(r[h_no]).strip()
        if not no_str:
            continue
        dt = _get(r, "tarih")
        a = agg.setdefault(no_str, {"count": 0, "first": None, "last": None})
        a["count"] += 1
        if dt:
            if a["first"] is None or dt < a["first"]:
                a["first"] = dt
            if a["last"] is None or dt > a["last"]:
                a["last"] = dt
        # Detail row
        vals = {k: _get(r, k) for k in cols}
        # hash bazli dedup
        h_src = "|".join((no_str, vals.get("takip_no") or "",
                          vals.get("tarih") or "",
                          vals.get("olusturulma") or ""))
        row_hash = hashlib.md5(h_src.encode("utf-8")).hexdigest()
        con.execute("""
            INSERT INTO bk_obstetri_visits
              (bk_hasta_no, takip_no, tarih, usg_age, efw, amnion, plasenta,
               serviks, hb, hct, mcv, plt, tit, diger, kilo, ta, sikayet,
               olusturulma, guncelleme, row_hash)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(row_hash) DO UPDATE SET
              usg_age=excluded.usg_age, efw=excluded.efw,
              amnion=excluded.amnion, plasenta=excluded.plasenta,
              serviks=excluded.serviks, hb=excluded.hb, hct=excluded.hct,
              mcv=excluded.mcv, plt=excluded.plt, tit=excluded.tit,
              diger=excluded.diger, kilo=excluded.kilo, ta=excluded.ta,
              sikayet=excluded.sikayet, guncelleme=excluded.guncelleme
        """, (no_str, vals.get("takip_no"), vals.get("tarih"),
              vals.get("usg_age"), vals.get("efw"), vals.get("amnion"),
              vals.get("plasenta"), vals.get("serviks"), vals.get("hb"),
              vals.get("hct"), vals.get("mcv"), vals.get("plt"),
              vals.get("tit"), vals.get("diger"), vals.get("kilo"),
              vals.get("ta"), vals.get("sikayet"),
              vals.get("olusturulma"), vals.get("guncelleme"), row_hash))
        detail_ins += 1

    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ins, upd = 0, 0
    for no, a in agg.items():
        existing = con.execute(
            "SELECT bk_hasta_no FROM bk_obstetri_index WHERE bk_hasta_no = ?",
            (no,)).fetchone()
        con.execute("""
            INSERT INTO bk_obstetri_index
              (bk_hasta_no, visit_count, last_visit, first_visit, updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(bk_hasta_no) DO UPDATE SET
              visit_count=excluded.visit_count,
              last_visit=excluded.last_visit,
              first_visit=excluded.first_visit,
              updated_at=excluded.updated_at
        """, (no, a["count"], a["last"], a["first"], now_iso))
        if existing:
            upd += 1
        else:
            ins += 1
    con.commit()
    _safe_print(f"  [obstetri-detail] {detail_ins} satir upsert")
    return ins, upd


def import_tahsilatlar_csv(con: sqlite3.Connection, path: str) -> int:
    """Tahsilatlar.csv -> bk_payments. row_hash ile dedup."""
    if not os.path.exists(path):
        return 0
    import hashlib
    hdr, rows = read_csv(path)
    H = {c: i for i, c in enumerate(hdr)}
    needed = ("Protokol_No", "Hasta_No", "Hasta_Adı", "Hasta_Soyadı",
              "Ödenen_Miktar", "Cinsi", "Tarihi")
    missing = [c for c in needed if c not in H]
    if missing:
        _safe_print(f"  [UYARI] tahsilat eksik kolon: {missing}")
        return 0
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ins = 0
    for row in rows:
        if len(row) < len(hdr):
            row = row + [''] * (len(hdr) - len(row))
        pno = row[H["Protokol_No"]]
        hno = row[H["Hasta_No"]]
        had = row[H["Hasta_Adı"]]
        hsd = row[H["Hasta_Soyadı"]]
        odn = row[H["Ödenen_Miktar"]]
        cns = row[H["Cinsi"]]
        trh = row[H["Tarihi"]]
        h_src = "|".join((pno, hno, odn, trh))
        row_hash = hashlib.md5(h_src.encode("utf-8")).hexdigest()
        try:
            con.execute("""
                INSERT INTO bk_payments
                  (protokol_no, bk_hasta_no, hasta_ad, hasta_soyad, odenen,
                   cinsi, tarih, row_hash, imported_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(row_hash) DO NOTHING
            """, (pno, hno, had, hsd, odn, cns, trh, row_hash, now_iso))
            if con.total_changes:
                ins += 1
        except Exception:
            pass
    con.commit()
    return ins


def import_medical_csv(con: sqlite3.Connection, path: str) -> int:
    if not path or not os.path.exists(path):
        return 0
    rows = _read_csv_dicts(path)
    lookup = _protocol_patient_lookup(con)
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    for row in rows:
        pno = _pick(row, "protokol_no")
        if not pno:
            continue
        bk_no = lookup.get(pno, "")
        con.execute("""
            INSERT INTO bk_medical_infos (
              protokol_no, bk_hasta_no, hasta_tc, hasta_ad, hasta_soyad,
              protokol_tarihi, hikayesi, sikayeti, ozgecmis, soygecmis,
              bulgular, uygulamalar, oneriler, notlar, tani_kodlari,
              imported_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(protokol_no) DO UPDATE SET
              bk_hasta_no=excluded.bk_hasta_no,
              hasta_tc=excluded.hasta_tc,
              hasta_ad=excluded.hasta_ad,
              hasta_soyad=excluded.hasta_soyad,
              protokol_tarihi=excluded.protokol_tarihi,
              hikayesi=excluded.hikayesi,
              sikayeti=excluded.sikayeti,
              ozgecmis=excluded.ozgecmis,
              soygecmis=excluded.soygecmis,
              bulgular=excluded.bulgular,
              uygulamalar=excluded.uygulamalar,
              oneriler=excluded.oneriler,
              notlar=excluded.notlar,
              tani_kodlari=excluded.tani_kodlari,
              imported_at=excluded.imported_at
        """, (
            pno, bk_no, _pick(row, "hasta_kimlik_numarasi"),
            _pick(row, "hasta_adi"), _pick(row, "hasta_soyadi"),
            _pick(row, "protokol_tarihi"), _pick(row, "hikayesi"),
            _pick(row, "sikayeti"), _pick(row, "ozgecmis"),
            _pick(row, "soygecmis"), _pick(row, "bulgular"),
            _pick(row, "uygulamalar"), _pick(row, "oneriler"),
            _pick(row, "notlar"), _pick(row, "tani_kodlari"), now_iso,
        ))
        count += 1
    con.commit()
    return count


def import_services_csv(con: sqlite3.Connection, path: str) -> int:
    if not path or not os.path.exists(path):
        return 0
    rows = _read_csv_dicts(path)
    lookup = _protocol_patient_lookup(con)
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    for row in rows:
        pno = _pick(row, "protokol_no")
        service_no = _pick(row, "hizmet_no")
        service_name = _pick(row, "hizmet_adi")
        service_date = _pick(row, "islem_tarihi")
        if not (pno or service_no or service_name):
            continue
        row_hash = _hash_values(pno, service_no, service_name, service_date)
        con.execute("""
            INSERT INTO bk_services (
              row_hash, protokol_no, bk_hasta_no, hizmet_no, hasta_ad,
              islem_tarihi, hizmet_adi, grup_adi, adet, hasta_tutari,
              kurum_tutari, indirim_tutari, tahsilat_tutari, imported_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(row_hash) DO UPDATE SET
              bk_hasta_no=excluded.bk_hasta_no,
              hasta_ad=excluded.hasta_ad,
              islem_tarihi=excluded.islem_tarihi,
              hizmet_adi=excluded.hizmet_adi,
              grup_adi=excluded.grup_adi,
              adet=excluded.adet,
              hasta_tutari=excluded.hasta_tutari,
              kurum_tutari=excluded.kurum_tutari,
              indirim_tutari=excluded.indirim_tutari,
              tahsilat_tutari=excluded.tahsilat_tutari,
              imported_at=excluded.imported_at
        """, (
            row_hash, pno, lookup.get(pno, ""), service_no,
            _pick(row, "hasta_adi"), service_date, service_name,
            _pick(row, "grup_adi"), _pick(row, "adet"),
            _pick(row, "hasta_tutari"), _pick(row, "kurum_tutari"),
            _pick(row, "indirim_tutari"), _pick(row, "tahsilat_tutari"),
            now_iso,
        ))
        count += 1
    con.commit()
    return count


def import_appointments_csv(con: sqlite3.Connection, path: str) -> int:
    if not path or not os.path.exists(path):
        return 0
    rows = _read_csv_dicts(path)
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    for row in rows:
        bk_no = _pick(row, "hasta_no")
        start = _pick(row, "randevu_baslangic")
        title = _pick(row, "randevu_basligi")
        if not (bk_no or start or title):
            continue
        row_hash = _hash_values(bk_no, start, _pick(row, "doktor_adi"), title)
        con.execute("""
            INSERT INTO bk_appointments (
              row_hash, bk_hasta_no, hasta_ad, hasta_soyad, telefon,
              baslangic, bitis, randevu_tipi, baslik, not_text, durum,
              doktor, kaynak, imported_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(row_hash) DO UPDATE SET
              hasta_ad=excluded.hasta_ad,
              hasta_soyad=excluded.hasta_soyad,
              telefon=excluded.telefon,
              baslangic=excluded.baslangic,
              bitis=excluded.bitis,
              randevu_tipi=excluded.randevu_tipi,
              baslik=excluded.baslik,
              not_text=excluded.not_text,
              durum=excluded.durum,
              doktor=excluded.doktor,
              kaynak=excluded.kaynak,
              imported_at=excluded.imported_at
        """, (
            row_hash, bk_no, _pick(row, "hasta_adi"),
            _pick(row, "hasta_soyadi"), _pick(row, "telefon_numarasi"),
            start, _pick(row, "randevu_bitis"), _pick(row, "randevu_tipi"),
            title, _pick(row, "randevu_notu"), _pick(row, "randevu_durumu"),
            _pick(row, "doktor_adi"), _pick(row, "kaynak"), now_iso,
        ))
        count += 1
    con.commit()
    return count


def _sheet_rows(path: str, preferred_sheet: str) -> tuple[list[str], list[tuple]]:
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[preferred_sheet] if preferred_sheet in wb.sheetnames else wb.active
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not rows:
        return [], []
    hdr = [str(x or "").strip() for x in rows[0]]
    return hdr, rows[1:]


def _xlsx_row_dict(header: list[str], row: tuple) -> dict:
    keys = [_norm_key(h) for h in header]
    return {keys[i]: (row[i] if i < len(row) and row[i] is not None else "")
            for i in range(len(keys))}


def import_obstetri_tracking_xlsx(con: sqlite3.Connection, path: str) -> tuple[int, int]:
    if not path or not os.path.exists(path):
        return 0, 0
    try:
        hdr, rows = _sheet_rows(path, "Obstetri Tracking")
    except ImportError:
        _safe_print("  [SKIP] openpyxl yok, obstetri tracking atlandi")
        return 0, 0
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    agg = {}
    detail = 0
    for raw in rows:
        row = _xlsx_row_dict(hdr, raw)
        bk_no = _pick(row, "hasta_no")
        if not bk_no:
            continue
        takip_no = _pick(row, "takip_numarasi")
        tarih = _pick(row, "takip_tarihi", "tarih")
        row_hash = _hash_values(bk_no, takip_no, tarih, _pick(row, "olusturulma_tarihi"))
        vals = {
            "usg_age": _pick(row, "usg_age"),
            "efw": _pick(row, "efw"),
            "amnion": _pick(row, "amnion"),
            "plasenta": _pick(row, "plasenta"),
            "serviks": _pick(row, "serviks"),
            "hb": _pick(row, "hb"),
            "hct": _pick(row, "hct"),
            "mcv": _pick(row, "mcv"),
            "plt": _pick(row, "plt"),
            "tit": _pick(row, "tit"),
            "diger": _pick(row, "diger"),
            "kilo": _pick(row, "kilo"),
            "ta": _pick(row, "ta"),
            "sikayet": _pick(row, "sikayet"),
            "olusturulma": _pick(row, "olusturulma_tarihi"),
            "guncelleme": _pick(row, "guncelleme_tarihi"),
        }
        con.execute("""
            INSERT INTO bk_obstetri_visits
              (bk_hasta_no, takip_no, tarih, usg_age, efw, amnion, plasenta,
               serviks, hb, hct, mcv, plt, tit, diger, kilo, ta, sikayet,
               olusturulma, guncelleme, row_hash)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(row_hash) DO UPDATE SET
              usg_age=excluded.usg_age, efw=excluded.efw,
              amnion=excluded.amnion, plasenta=excluded.plasenta,
              serviks=excluded.serviks, hb=excluded.hb, hct=excluded.hct,
              mcv=excluded.mcv, plt=excluded.plt, tit=excluded.tit,
              diger=excluded.diger, kilo=excluded.kilo, ta=excluded.ta,
              sikayet=excluded.sikayet, guncelleme=excluded.guncelleme
        """, (
            bk_no, takip_no, tarih, vals["usg_age"], vals["efw"],
            vals["amnion"], vals["plasenta"], vals["serviks"], vals["hb"],
            vals["hct"], vals["mcv"], vals["plt"], vals["tit"],
            vals["diger"], vals["kilo"], vals["ta"], vals["sikayet"],
            vals["olusturulma"], vals["guncelleme"], row_hash,
        ))
        a = agg.setdefault(bk_no, {"count": 0, "first": "", "last": ""})
        a["count"] += 1
        if tarih:
            if not a["first"] or tarih < a["first"]:
                a["first"] = tarih
            if not a["last"] or tarih > a["last"]:
                a["last"] = tarih
        detail += 1
    inserted, updated = 0, 0
    for bk_no, a in agg.items():
        exists = con.execute(
            "SELECT 1 FROM bk_obstetri_index WHERE bk_hasta_no=?",
            (bk_no,)).fetchone()
        con.execute("""
            INSERT INTO bk_obstetri_index
              (bk_hasta_no, visit_count, last_visit, first_visit, updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(bk_hasta_no) DO UPDATE SET
              visit_count=excluded.visit_count,
              last_visit=excluded.last_visit,
              first_visit=excluded.first_visit,
              updated_at=excluded.updated_at
        """, (bk_no, a["count"], a["last"], a["first"], now_iso))
        if exists:
            updated += 1
        else:
            inserted += 1
    con.commit()
    _safe_print(f"  [obstetri-tracking] {detail} satir upsert")
    return inserted, updated


def import_gynecology_xlsx(con: sqlite3.Connection, path: str) -> tuple[int, int]:
    if not path or not os.path.exists(path):
        return 0, 0
    try:
        hdr, rows = _sheet_rows(path, "Gynecology Resume")
        thdr, trows = _sheet_rows(path, "Gynecology Tracking")
    except ImportError:
        _safe_print("  [SKIP] openpyxl yok, jinekoloji import atlandi")
        return 0, 0
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resume_count = 0
    for raw in rows:
        row = _xlsx_row_dict(hdr, raw)
        bk_no = _pick(row, "hasta_no")
        resume_no = _pick(row, "resume_no")
        pno = _pick(row, "protokol_numarasi")
        tarih = _pick(row, "tarih")
        if not (bk_no or resume_no or pno):
            continue
        data_json = json.dumps(row, ensure_ascii=False, default=str,
                               separators=(",", ":"))
        row_hash = _hash_values(bk_no, pno, resume_no, tarih)
        bulgular = "\n".join(
            x for x in (
                _pick(row, "spekulum"),
                _pick(row, "uterus"),
                _pick(row, "uterus_ve_adneks"),
                _pick(row, "batin"),
                _pick(row, "sag_over"),
                _pick(row, "sol_over"),
                _pick(row, "diger_bulgular"),
                _pick(row, "diger_goruntuleme"),
            ) if x)
        con.execute("""
            INSERT INTO bk_gynecology_resume (
              row_hash, bk_hasta_no, protokol_no, resume_no, tarih,
              son_adet_tarihi, sikayet_oyku, bulgular, notlar, tani,
              tedavi_plani, recete, sonuc, data_json, imported_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(row_hash) DO UPDATE SET
              tarih=excluded.tarih,
              son_adet_tarihi=excluded.son_adet_tarihi,
              sikayet_oyku=excluded.sikayet_oyku,
              bulgular=excluded.bulgular,
              notlar=excluded.notlar,
              tani=excluded.tani,
              tedavi_plani=excluded.tedavi_plani,
              recete=excluded.recete,
              sonuc=excluded.sonuc,
              data_json=excluded.data_json,
              imported_at=excluded.imported_at
        """, (
            row_hash, bk_no, pno, resume_no, tarih,
            _pick(row, "son_adet_tarihi"), _pick(row, "sikayet_oyku"),
            bulgular, _pick(row, "notlar"), _pick(row, "tani"),
            _pick(row, "tedavi_plani"), _pick(row, "recete"),
            _pick(row, "sonuc"), data_json, now_iso,
        ))
        resume_count += 1

    tracking_count = 0
    for raw in trows:
        row = _xlsx_row_dict(thdr, raw)
        bk_no = _pick(row, "hasta_no")
        takip_no = _pick(row, "takip_numarasi")
        tarih = _pick(row, "tarih")
        if not (bk_no or takip_no or tarih):
            continue
        data_json = json.dumps(row, ensure_ascii=False, default=str,
                               separators=(",", ":"))
        row_hash = _hash_values(bk_no, _pick(row, "resume_no"), takip_no, tarih)
        con.execute("""
            INSERT INTO bk_gynecology_tracking (
              row_hash, bk_hasta_no, resume_no, takip_no, tarih, usg_age,
              efw, amnion, plasenta, serviks, hb, hct, mcv, plt, tit,
              diger, kilo, ta, sikayet, data_json, imported_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(row_hash) DO UPDATE SET
              tarih=excluded.tarih,
              usg_age=excluded.usg_age,
              efw=excluded.efw,
              amnion=excluded.amnion,
              plasenta=excluded.plasenta,
              serviks=excluded.serviks,
              hb=excluded.hb,
              hct=excluded.hct,
              mcv=excluded.mcv,
              plt=excluded.plt,
              tit=excluded.tit,
              diger=excluded.diger,
              kilo=excluded.kilo,
              ta=excluded.ta,
              sikayet=excluded.sikayet,
              data_json=excluded.data_json,
              imported_at=excluded.imported_at
        """, (
            row_hash, bk_no, _pick(row, "resume_no"), takip_no, tarih,
            _pick(row, "usg_age"), _pick(row, "efw"), _pick(row, "amnion"),
            _pick(row, "plasenta"), _pick(row, "serviks"), _pick(row, "hb"),
            _pick(row, "hct"), _pick(row, "mcv"), _pick(row, "plt"),
            _pick(row, "tit"), _pick(row, "diger"), _pick(row, "kilo", "kio"),
            _pick(row, "ta"), _pick(row, "sikayet"), data_json, now_iso,
        ))
        tracking_count += 1
    con.commit()
    return resume_count, tracking_count


def run_import(since_days: int, dry_run: bool,
               exports_dir: str | None = None,
               mode: str = "since"):
    """mode:
      'since'    -> son N gun protokolu olan hastalar (default, hizli)
      'all'      -> TUM hastalar + TUM protokoller (full sync, en yavas)
      'missing'  -> sadece DB'de olmayan hastalar (incremental, hizli)
    """
    today = datetime.datetime.now()
    cutoff = today - datetime.timedelta(days=since_days)
    _safe_print(f"\n=== BulutKlinik Import (mode={mode}) ===")
    _safe_print(f"  Bugun: {today:%Y-%m-%d}")
    if mode == "since":
        _safe_print(f"  Kesim: {cutoff:%Y-%m-%d} (son {since_days} gun)")
    elif mode == "all":
        _safe_print(f"  Mode: ALL - tum hastalar + tum protokoller (tarih filtresi yok)")
    elif mode == "missing":
        _safe_print(f"  Mode: MISSING - sadece DB'de olmayan hastalar")
    _safe_print(f"  Dry run: {dry_run}")

    # 1) Indir veya verilen export klasorunu oku
    if exports_dir is None:
        stamp = today.strftime("%Y%m%d_%H%M%S")
        exports_dir = rf"D:\YazKlinik_Final_D300\bk_exports\{stamp}_import"
        _safe_print(f"\n[1/4] CSV/XLSX indir -> {exports_dir}")
        dl = download_fresh(exports_dir)
    else:
        _safe_print(f"\n[1/4] Mevcut CSV/XLSX oku -> {exports_dir}")
        dl = _existing_exports_manifest(exports_dir)
    if not dl.get("ok"):
        _safe_print(f"  HATA: {dl.get('error')}")
        return 1

    hastalar_path = dl["files"]["hastalar"]["path"]
    protokoller_path = dl["files"]["protokoller"]["path"]

    # 2) Protokolleri oku, son 3 ay filtre
    _safe_print(f"\n[2/4] Protokoller.csv oku + tarih filtre")
    p_hdr, p_rows = read_csv(protokoller_path)
    _safe_print(f"  Toplam protokol: {len(p_rows)}")
    _safe_print(f"  Header: {p_hdr}")
    # Header column index
    H = {col: i for i, col in enumerate(p_hdr)}
    needed = ("Protokol No", "İsim", "Soyisim", "Baba Adı", "Anne Adı",
              "Anne TC No", "Anlaşmalı Kurum", "Branş", "Doktor",
              "Hasta No", "Protokol Tarihi", "Protokol Tipi", "Geliş Nedeni")
    missing = [c for c in needed if c not in H]
    if missing:
        _safe_print(f"  EKSIK kolon: {missing}")
        return 2

    recent_protocols = []
    target_hasta_nos = set()
    skipped_old = 0
    skipped_nodate = 0
    for row in p_rows:
        if len(row) < len(p_hdr):
            row = row + [''] * (len(p_hdr) - len(row))
        date_str = row[H["Protokol Tarihi"]]
        d = parse_date(date_str)
        if mode == "since":
            if d is None:
                skipped_nodate += 1
                continue
            if d < cutoff:
                skipped_old += 1
                continue
        rec = {k: row[H[k]] for k in needed}
        recent_protocols.append(rec)
        if rec["Hasta No"]:
            target_hasta_nos.add(rec["Hasta No"])

    _safe_print(f"  Aday protokol: {len(recent_protocols)}")
    if mode == "since":
        _safe_print(f"  Filtrelenmis (eski): {skipped_old}")
        _safe_print(f"  Filtrelenmis (tarihsiz): {skipped_nodate}")
    _safe_print(f"  Unique protokollu hasta sayisi: {len(target_hasta_nos)}")

    # 3) Hastalar.csv'den seim
    _safe_print(f"\n[3/4] Hastalar.csv oku + secim")
    h_hdr, h_rows = read_csv(hastalar_path)
    _safe_print(f"  Toplam hasta (CSV): {len(h_rows)}")
    HH = {col: i for i, col in enumerate(h_hdr)}
    if "Hasta No" not in HH:
        _safe_print(f"  EKSIK 'Hasta No' kolonu")
        return 3

    # Mode'a gore hasta seimi
    db_existing_nos = set()
    if mode == "missing":
        try:
            con0 = sqlite3.connect(DB_PATH, timeout=10)
            db_existing_nos = set(
                r[0] for r in con0.execute(
                    "SELECT bk_hasta_no FROM bk_patients").fetchall() if r[0])
            con0.close()
            _safe_print(f"  DB'de mevcut hasta: {len(db_existing_nos)}")
        except Exception as ex:
            _safe_print(f"  DB read fail: {ex}")

    selected_patients = []
    for row in h_rows:
        if len(row) < len(h_hdr):
            row = row + [''] * (len(h_hdr) - len(row))
        hno = row[HH["Hasta No"]]
        take = False
        if mode == "all":
            take = bool(hno)
        elif mode == "missing":
            take = bool(hno) and hno not in db_existing_nos
        else:  # since
            take = hno in target_hasta_nos
        if take:
            selected_patients.append({k: row[HH[k]] for k in h_hdr if k in HH})
    _safe_print(f"  Secilen hasta: {len(selected_patients)}")

    # Mode missing'de: protokol listesi de DB'de olmayan hastalarla sinirla
    if mode == "missing":
        selected_set = set(p.get("Hasta No") for p in selected_patients)
        # mevcut DB hastalarinin yeni protokollerini de al
        all_relevant_nos = selected_set | db_existing_nos
        recent_protocols = [p for p in recent_protocols
                            if p["Hasta No"] in all_relevant_nos]
        _safe_print(f"  Mode missing: filtreli protokol={len(recent_protocols)}")
    elif mode == "all":
        _safe_print(f"  Mode all: tum protokol cekilecek={len(recent_protocols)}")

    # 4) DB'ye yaz
    _safe_print(f"\n[4/4] SQLite upsert ({DB_PATH})")
    if dry_run:
        _safe_print("  DRY-RUN: yazma atlandi.")
        _safe_print(f"\n  ORNEK 3 hasta:")
        for p in selected_patients[:3]:
            _safe_print(f"    {p.get('Adı','')} {p.get('Soyadı','')} "
                  f"(No: {p.get('Hasta No')}, TC: {p.get('Kimlik Numarası','')})")
        _safe_print(f"\n  ORNEK 3 protokol:")
        for p in recent_protocols[:3]:
            _safe_print(f"    #{p['Protokol No']} {p['İsim']} {p['Soyisim']} - "
                  f"{p['Protokol Tarihi']} - {p['Protokol Tipi']}")
        return 0

    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    ensure_schema(con)
    now_iso = today.strftime("%Y-%m-%d %H:%M:%S")
    # Hasta upsert
    pat_ins, pat_upd = 0, 0
    for p in selected_patients:
        hno = p.get("Hasta No")
        if not hno:
            continue
        existing = con.execute(
            "SELECT bk_hasta_no FROM bk_patients WHERE bk_hasta_no = ?",
            (hno,)).fetchone()
        params = (
            hno,
            p.get("Kimlik Numarası", ""),
            p.get("Adı", ""),
            p.get("Soyadı", ""),
            p.get("Cinsiyeti", ""),
            p.get("Uyruğu", ""),
            p.get("Pasaport Numarası", ""),
            p.get("Geliş Tarihi", ""),
            p.get("Özgeçmiş", ""),
            p.get("Soygeçmiş", ""),
            p.get("Alerjiler", ""),
            p.get("Geliş Nedeni", ""),
            p.get("Adres", ""),
            p.get("Doğum Tarihi", ""),
            p.get("Doğum Yeri", ""),
            p.get("Telefon No", ""),
            p.get("Eposta", ""),
            p.get("Kan Grubu", ""),
            p.get("Baba Adı", ""),
            p.get("Anne Adı", ""),
            p.get("Medeni Hali", ""),
            p.get("Not", ""),
            p.get("Anlaşmalı Kurum", ""),
            now_iso, now_iso,
        )
        con.execute("""
            INSERT INTO bk_patients (
              bk_hasta_no, tc_kimlik, ad, soyad, cinsiyet, uyruk,
              pasaport_no, gelis_tarihi, ozgecmis, soygecmis, alerjiler,
              gelis_nedeni, adres, dogum_tarihi, dogum_yeri, telefon,
              eposta, kan_grubu, baba_adi, anne_adi, medeni_hali, not_text,
              anlasmali_kurum, imported_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(bk_hasta_no) DO UPDATE SET
              tc_kimlik=excluded.tc_kimlik, ad=excluded.ad, soyad=excluded.soyad,
              cinsiyet=excluded.cinsiyet, uyruk=excluded.uyruk,
              pasaport_no=excluded.pasaport_no, gelis_tarihi=excluded.gelis_tarihi,
              ozgecmis=excluded.ozgecmis, soygecmis=excluded.soygecmis,
              alerjiler=excluded.alerjiler, gelis_nedeni=excluded.gelis_nedeni,
              adres=excluded.adres, dogum_tarihi=excluded.dogum_tarihi,
              dogum_yeri=excluded.dogum_yeri, telefon=excluded.telefon,
              eposta=excluded.eposta, kan_grubu=excluded.kan_grubu,
              baba_adi=excluded.baba_adi, anne_adi=excluded.anne_adi,
              medeni_hali=excluded.medeni_hali, not_text=excluded.not_text,
              anlasmali_kurum=excluded.anlasmali_kurum,
              updated_at=excluded.updated_at
        """, params)
        if existing:
            pat_upd += 1
        else:
            pat_ins += 1

    # Protokol upsert
    prt_ins, prt_upd = 0, 0
    for p in recent_protocols:
        pno = p["Protokol No"]
        if not pno:
            continue
        existing = con.execute(
            "SELECT protokol_no FROM bk_protocols WHERE protokol_no = ?",
            (pno,)).fetchone()
        params = (pno, p["Hasta No"], p["İsim"], p["Soyisim"],
                  p["Baba Adı"], p["Anne Adı"], p["Anne TC No"],
                  p["Anlaşmalı Kurum"], p["Branş"], p["Doktor"],
                  p["Protokol Tarihi"], p["Protokol Tipi"],
                  p["Geliş Nedeni"], now_iso)
        con.execute("""
            INSERT INTO bk_protocols (
              protokol_no, bk_hasta_no, isim, soyisim, baba_adi, anne_adi,
              anne_tc_no, anlasmali_kurum, brans, doktor, protokol_tarihi,
              protokol_tipi, gelis_nedeni, imported_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(protokol_no) DO UPDATE SET
              bk_hasta_no=excluded.bk_hasta_no, isim=excluded.isim,
              soyisim=excluded.soyisim, baba_adi=excluded.baba_adi,
              anne_adi=excluded.anne_adi, anne_tc_no=excluded.anne_tc_no,
              anlasmali_kurum=excluded.anlasmali_kurum, brans=excluded.brans,
              doktor=excluded.doktor, protokol_tarihi=excluded.protokol_tarihi,
              protokol_tipi=excluded.protokol_tipi,
              gelis_nedeni=excluded.gelis_nedeni
        """, params)
        if existing:
            prt_upd += 1
        else:
            prt_ins += 1

    con.commit()

    # Obstetri.xlsx -> bk_obstetri_index (gebe tespiti) + bk_obstetri_visits (detay)
    obs_path = dl["files"].get("obstetri", {}).get("path") if dl.get("files") else None
    obs_ins, obs_upd = 0, 0
    if obs_path and os.path.exists(obs_path):
        _safe_print(f"\n[5/6] Obstetri index + detail (xlsx)")
        try:
            obs_ins, obs_upd = import_obstetri_tracking_xlsx(con, obs_path)
            _safe_print(f"  +{obs_ins} yeni gebe, {obs_upd} guncellenen")
        except Exception as ex:
            _safe_print(f"  [HATA] obstetri import: {ex}")
    else:
        _safe_print(f"\n[5/6] Obstetri xlsx yok, atlandi")

    # Tahsilatlar.csv -> bk_payments
    tah_path = dl["files"].get("tahsilatlar", {}).get("path") if dl.get("files") else None
    tah_ins = 0
    if tah_path and os.path.exists(tah_path):
        _safe_print(f"\n[6/6] Tahsilatlar (csv) -> bk_payments")
        try:
            tah_ins = import_tahsilatlar_csv(con, tah_path)
            _safe_print(f"  +{tah_ins} yeni odeme kaydi")
        except Exception as ex:
            _safe_print(f"  [HATA] tahsilat import: {ex}")
    else:
        _safe_print(f"\n[6/6] Tahsilatlar csv yok, atlandi")

    # D300 clinical export katmani: BK'daki gelis iceriği, hizmet,
    # randevu ve jinekoloji recete/takip bilgileri Voluson tarafinda
    # okunabilir hale gelsin diye yerel tablolara alinır.
    med_count = svc_count = appt_count = gyn_resume_count = gyn_track_count = 0
    med_path = dl["files"].get("medikal", {}).get("path") if dl.get("files") else None
    svc_path = dl["files"].get("hizmetler", {}).get("path") if dl.get("files") else None
    appt_path = dl["files"].get("randevular", {}).get("path") if dl.get("files") else None
    gyn_path = dl["files"].get("jinekoloji", {}).get("path") if dl.get("files") else None
    if med_path and os.path.exists(med_path):
        try:
            med_count = import_medical_csv(con, med_path)
        except Exception as ex:
            _safe_print(f"  [HATA] medikal import: {ex}")
    if svc_path and os.path.exists(svc_path):
        try:
            svc_count = import_services_csv(con, svc_path)
        except Exception as ex:
            _safe_print(f"  [HATA] hizmet import: {ex}")
    if appt_path and os.path.exists(appt_path):
        try:
            appt_count = import_appointments_csv(con, appt_path)
        except Exception as ex:
            _safe_print(f"  [HATA] randevu import: {ex}")
    if gyn_path and os.path.exists(gyn_path):
        try:
            gyn_resume_count, gyn_track_count = import_gynecology_xlsx(con, gyn_path)
        except Exception as ex:
            _safe_print(f"  [HATA] jinekoloji import: {ex}")

    # Final count
    total_p = con.execute("SELECT COUNT(*) FROM bk_patients").fetchone()[0]
    total_pr = con.execute("SELECT COUNT(*) FROM bk_protocols").fetchone()[0]
    total_obs = con.execute("SELECT COUNT(*) FROM bk_obstetri_index").fetchone()[0]
    total_ov = con.execute("SELECT COUNT(*) FROM bk_obstetri_visits").fetchone()[0]
    total_pay = con.execute("SELECT COUNT(*) FROM bk_payments").fetchone()[0]
    total_med = con.execute("SELECT COUNT(*) FROM bk_medical_infos").fetchone()[0]
    total_svc = con.execute("SELECT COUNT(*) FROM bk_services").fetchone()[0]
    total_gyn = con.execute("SELECT COUNT(*) FROM bk_gynecology_resume").fetchone()[0]
    con.close()

    # BK kaydi Voluson/YazKlinik DB tarafinda mutlaka gorunsun.
    # Bu adim DB-only calisir; NAS klasoru olusturmaz.
    global LAST_MIRROR_STATS
    LAST_MIRROR_STATS = None
    try:
        import yazklinik_bk_voluson_mirror as _bkm
        LAST_MIRROR_STATS = _bkm.mirror_bk_patients(
            db_path=DB_PATH, dry_run=False, user="bk-import")
    except Exception as ex:
        _safe_print(f"  [HATA] BK -> Voluson DB mirror: {ex}")
        return 7

    _safe_print(f"\n=== TAMAM ===")
    _safe_print(f"  Hasta: +{pat_ins} yeni, {pat_upd} guncellenen "
          f"(bk_patients toplam: {total_p})")
    _safe_print(f"  Protokol: +{prt_ins} yeni, {prt_upd} guncellenen "
          f"(bk_protocols toplam: {total_pr})")
    _safe_print(f"  Obstetri index: {total_obs} hasta, "
          f"visits detay: {total_ov}")
    _safe_print(f"  Tahsilat (bk_payments): {total_pay} kayit")
    _safe_print(f"  Medikal/Hizmet/Jinekoloji: {total_med} / {total_svc} / {total_gyn} kayit")
    if any((med_count, svc_count, appt_count, gyn_resume_count, gyn_track_count)):
        _safe_print("  Bu importta klinik detay: "
              f"medikal={med_count}, hizmet={svc_count}, "
              f"randevu={appt_count}, gyn={gyn_resume_count}, "
              f"gyn_takip={gyn_track_count}")
    if LAST_MIRROR_STATS:
        _safe_print("  BK -> Voluson DB: "
              f"+{LAST_MIRROR_STATS.get('created_patients', 0)} DB-only hasta, "
              f"+{LAST_MIRROR_STATS.get('created_links', 0)} link, "
              f"{LAST_MIRROR_STATS.get('auto_linked_existing', 0)} mevcut eslesme")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=90,
                    help="Son N gun (default 90 = 3 ay)")
    ap.add_argument("--mode", choices=("since", "all", "missing"),
                    default="since",
                    help="since=son N gun, all=hepsi, missing=DB'de olmayan")
    ap.add_argument("--dry-run", action="store_true",
                    help="Sadece analiz, DB yazma")
    ap.add_argument("--exports-dir", default=None,
                    help="Mevcut export klasoru kullan (indirme atla)")
    args = ap.parse_args()
    return run_import(args.since, args.dry_run, args.exports_dir, mode=args.mode)


if __name__ == "__main__":
    # CLI: UTF-8 stdout (Windows cp1252 fallback'ten kacin)
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer,
                                       encoding='utf-8', errors='replace')
    except Exception:
        pass
    sys.exit(main())
