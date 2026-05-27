#!/usr/bin/env python3
"""
YazKlinik Onam Form Import - klasoru tarar, kategorize eder, DB'ye yukler.

Kullanim:
    python tools/onam_import.py "C:\\Path\\to\\Onam_Klasoru"

Veya kuru bekleme (henuz yukleme yapma):
    python tools/onam_import.py "C:\\Path\\to\\Onam_Klasoru" --dry-run
"""
from __future__ import annotations
import argparse
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

DB_PATH = r"D:\YazKlinik_Final_D250\local_db\yazklinik_v68.sqlite3"

# Kategori belirleyici anahtar kelimeler (kucuk harfli aranir)
CATEGORY_KEYWORDS = {
    "obstetric": [
        "gebelik", "gebe", "sezeryan", "sezaryen", "dogum", "doğum",
        "nst", "ctg", "usg", "ultrason", "amniyo", "amnio", "amniyosentez",
        "cvs", "koryon", "abort", "kuretaj", "kürtaj", "tahliye",
        "iugr", "preeklampsi", "eklampsi", "gestasyonel", "trombo",
        "obs ", "obstetrik", "obstetrı", "anomali tarama",
        "tarama testi", "ikili test", "uclu test", "dortlu test",
        "fetal", "fetus", "embriyo", "makat", "vakum", "forseps",
        "epizyo", "epizyotomi", "cerrahi gebelik", "ectopic", "tüp",
        "tüp gebelik", "molar", "mol gebelik", "iml", "mfm",
        "preterm", "postterm", "preimplantasyon", "doula", "luteal",
        "preimplant", "ivf gebelik", "rh", "antikor", "amniyon",
    ],
    "gynecologic": [
        "jinekoloji", "jinekolog", "jin ", "gyn",
        "histeroskopi", "histeroskop", "histerektomi",
        "laparoskopi", "laparoskop", "myomektomi", "miyomektomi",
        "polipektomi", "polip", "biyopsi", "biopsi",
        "over", "ovarian", "ovaryum", "kist", "kistektomi",
        "miyom", "myom", "endometriyozis", "endometrium",
        "hpv", "kolposkopi", "konizasyon", "leep", "cervix", "serviks",
        "vajinal", "vagina", "vulva", "perine", "labiap",
        "infertilite", "ivf", "tup bebek", "tüp bebek", "icsi",
        "ovulasyon", "ovulation", "ohss", "smear", "pap smear",
        "tomb", "tuboplasti", "salpenj", "salpingektomi", "ooforektomi",
        "ohss", "hsg", "histerosalpingografi", "estetik",
        "labioplasti", "vajinoplasti", "vajinal rejuvenasyon",
        "menopoz", "hormonal", "hormon", "iud", "rim", "kondom",
        "tubal ligasyon", "tubal sterilizasyon", "premenopozal",
        "postmenopozal", "yumurta", "endokrin",
    ],
}

# Genel onam (her ikisinden de) — anestezi, kan transfuzyonu, vs.
GENERAL_KEYWORDS = [
    "anestezi", "sedasyon", "lokal anestezi", "genel anestezi",
    "kan transfüzyon", "kan transfuzyon", "transfuzyon",
    "ameliyat", "operasyon", "cerrahi", "hastane yatis",
    "fotograf", "video", "kayıt", "kvkk", "kişisel veri",
    "konsultasyon", "ikinci görüş", "tedavi reddi",
]

SUPPORTED_EXT = {".pdf", ".doc", ".docx", ".txt", ".rtf"}


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    tr_map = str.maketrans("ığüşöç", "igusoc")
    return text.translate(tr_map)[:80]


def detect_category(filename: str, content_snippet: str = "",
                    parent_dir: str = "") -> tuple[str, str]:
    """
    Returns (category, purpose):
      category: Gebelik | Jinekoloji | Jinekolojik Estetik |
                Medikal Estetik | Infertilite | Paylasim Izinleri
      purpose:  okuyucu icin aciklama (Turkce)
    """
    haystack = f"{filename} {content_snippet} {parent_dir}".lower()
    # Kelimelerdeki Turkce karakterleri normalize et + mojibake
    for src, dst in zip("ığüşöçİĞÜŞÖÇ", "igusociIGUSOC"):
        haystack = haystack.replace(src, dst)
    # Mojibake'li donmus karakterler
    for bad in ("�", "ý", "þ"):
        haystack = haystack.replace(bad, "")

    # AGIR estetik kelimeler: bu sinyal varsa kesin aesthetic
    strong_aesthetic = [
        "botox", "botulinum", "botilinum",
        "dolgu", "filler", "mezoterapi", "mezo",
        "prp", "lipoliz", "lipo ",
        "hyaluron", "hyaluronidaz",
        "labioplasti", "labium major", "labium minor", "labia major",
        "vajinoplasti", "vajen daraltma", "vajinal rejuvenasyon",
        "kimyasal", "kimyasal soyma", "kimyasal cilt", "peeling",
        "lazer epilasyon", "epilasyon",
    ]
    if any(k in haystack for k in strong_aesthetic):
        if any(k in haystack for k in [
                "labioplasti", "labiaplasti", "labium major",
                "labium minor", "labia major", "labia minor",
                "vajinoplasti", "vajen daraltma",
                "vajinal rejuvenasyon"]):
            return "Jinekolojik Estetik", "Jinekolojik / intim estetik onam"
        return "Medikal Estetik", "Medikal estetik onam"

    # AGIR jinekoloji - over/bartholin/miyom/histeroskopi varsa kesin gynec
    strong_gynec = [
        "bartholin", "histeroskop", "laparoskop", "polipektomi",
        "ooforektomi", "miyom", "myom", "kistektomi",
        "kolposkop", "konizasyon", "leep",
    ]
    if any(k in haystack for k in strong_gynec):
        return "Jinekoloji", "Jinekoloji onam (cerrahi/girisim)"

    # AGIR obstetrik - gebelik/dogum/sezeryan/kuretaj/amnio
    strong_obs = [
        "gebelik", "gebe ", "hamile",
        "sezeryan", "sezaryen", "dogum",
        "kuretaj", "kürtaj", "tahliye gebelik",
        "amniyo", "amniosentez", "cvs",
        "down sendrom", "anomali tarama", "ikili test",
        "fetal", "fetus",
    ]
    if any(k in haystack for k in strong_obs):
        return "Gebelik", "Gebelik / obstetrik onam"

    # KESIN genel onam: SADECE FILENAME'e bak (content false-positive olmasin)
    fname_only = filename.lower()
    for src, dst in zip("ığüşöçİĞÜŞÖÇ", "igusociIGUSOC"):
        fname_only = fname_only.replace(src, dst)
    infertilite_kw = [
        "infertilite", "ivf", "tup bebek", "icsi", "ovulasyon",
        "ohss", "hsg", "histerosalpingografi", "embriyo transfer",
        "blastosist", "fertilite koruma", "yumurta toplama", "opu ",
    ]
    if any(k in haystack for k in infertilite_kw):
        return "Infertilite", "Infertilite / IVF onam"

    strong_general_fname = [
        "hastabilgilendirme", "hasta-bilgilendirme", "hasta_bilgilendirme",
        "kvkk", "kisisel-veri", "kayit-formu", "kayitformu",
        "fotograf", "fotoğraf", "video-onam",
        "anestezi", "transfuzyon", "transfüzyon",
    ]
    if any(k in fname_only for k in strong_general_fname):
        if any(k in fname_only for k in [
                "kvkk", "kisisel-veri", "kayit-formu", "kayitformu",
                "fotograf", "video-onam"]):
            return "Paylasim Izinleri", "Paylasim / KVKK / foto izin"
        return "Jinekoloji", "Genel jinekolojik / islem onami"

    # ESTETIK ozel kategori - botox/dolgu/PRP/mezoterapi/lazer epilasyon/lipoliz
    aesthetic_keywords = [
        "botox", "botulinum", "botilinum", "botulın",
        "dolgu", "filler", "hyaluron",
        "mezoterapi", "mesotherapy", "mezo",
        "prp",
        "lazer epilasyon", "laser epilasyon", "lazer", "epilasyon",
        "lipoliz", "lipo ", "lipoluk",
        "kimyasal", "kimyasal soyma", "kimyasal cilt", "peeling", "soyma",
        "estetik", "aesthetic", "aesthetik", "rejuvenasyon", "rejuvenation",
        "vajinoplasti", "labioplasti", "labium major", "labia major",
        "labium minor", "labium-minor", "labium-major", "vajen daraltma",
        # Parent klasor isimi de match etmeli
        "estetik-onam",
    ]
    aesthetic_score = sum(1 for k in aesthetic_keywords if k in haystack)
    # Parent klasor "estetik" iceriyor mu - guclu sinyal
    if "estetik" in parent_dir.lower():
        aesthetic_score += 3

    obs_score = sum(1 for k in CATEGORY_KEYWORDS["obstetric"] if k in haystack)
    gyn_score = sum(1 for k in CATEGORY_KEYWORDS["gynecologic"] if k in haystack)
    gen_score = sum(1 for k in GENERAL_KEYWORDS if k in haystack)

    # Estetik agir basiyorsa ayri kategori (klinik estetik onamlari)
    if aesthetic_score >= 1 and aesthetic_score >= obs_score:
        if any(k in haystack for k in [
                "labioplasti", "labiaplasti", "labium major",
                "labium minor", "labia major", "labia minor",
                "vajinoplasti", "vajen daraltma",
                "vajinal rejuvenasyon"]):
            return "Jinekolojik Estetik", "Jinekolojik / intim estetik onam"
        return "Medikal Estetik", "Medikal estetik onam"
    # Genel onam (anestezi/kan vs.) ama klinik baglam icermiyorsa "general"
    if gen_score > 0 and obs_score == 0 and gyn_score == 0 and aesthetic_score == 0:
        if any(k in haystack for k in ["kvkk", "kisisel veri", "fotograf", "video", "kayit", "paylasim"]):
            return "Paylasim Izinleri", "Paylasim / KVKK / foto izin"
        return "Jinekoloji", "Genel jinekolojik / islem onami"
    if obs_score > gyn_score:
        return "Gebelik", "Gebelik / obstetrik onam"
    if gyn_score > 0:
        return "Jinekoloji", "Jinekoloji onam"
    return "Jinekoloji", "Otomatik kategori (Jinekoloji - varsayilan)"


def read_content_snippet(path: Path, max_bytes: int = 4000) -> str:
    """PDF/Word'den ilk birkac KB text cikar, yoksa filename'e dus."""
    try:
        ext = path.suffix.lower()
        if ext == ".pdf":
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(str(path))
                text = ""
                for page in doc[:2]:
                    text += page.get_text() or ""
                    if len(text) > max_bytes:
                        break
                doc.close()
                return text[:max_bytes]
            except Exception:
                return ""
        if ext in (".txt",):
            return path.read_text(encoding="utf-8", errors="ignore")[:max_bytes]
        # docx icin python-docx olabilir, yoksa skip
        if ext == ".docx":
            try:
                from docx import Document  # type: ignore
                doc = Document(str(path))
                return "\n".join(p.text for p in doc.paragraphs[:30])[:max_bytes]
            except Exception:
                return ""
    except Exception:
        pass
    return ""


def main():
    # Print encoding fix - Turkce karakter Windows cp1254 cakismasin
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Onam form klasorunu DB'ye importla")
    parser.add_argument("folder", help="Onam dosyalarinin oldugu klasor")
    parser.add_argument("--dry-run", action="store_true",
                        help="Yapilacaklari listele ama DB'ye yazma")
    parser.add_argument("--db", default=DB_PATH, help="SQLite DB path")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.exists():
        print(f"[!] Klasor bulunamadi: {folder}")
        sys.exit(1)

    # Tum dosyalari recursive bul - bazi klasorleri dışla
    EXCLUDE_DIRS = {"#recycle", "turizm", "$recycle.bin", ".trash", "test", "tests"}
    EXCLUDE_FILES = {"print-color-test-page-basic-1.pdf", "astalife.jpg"}
    files = []
    for p in folder.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in SUPPORTED_EXT:
            continue
        # macOS metadata dosyalari (._xxx) atla
        if p.name.startswith("._"):
            continue
        # Thumbs.db / DS_Store gibi
        if p.name.lower() in {"thumbs.db", ".ds_store", "desktop.ini"}:
            continue
        # Cok kucuk (< 1KB) muhtemelen metadata
        try:
            if p.stat().st_size < 1024:
                continue
        except Exception:
            pass
        # Exclude dir check (any ancestor)
        if any(part.lower() in EXCLUDE_DIRS for part in p.parts):
            continue
        if p.name.lower() in EXCLUDE_FILES:
            continue
        files.append(p)
    files.sort()

    if not files:
        print(f"[!] Klasorde desteklenen dosya yok: {folder}")
        print(f"    Desteklenen: {sorted(SUPPORTED_EXT)}")
        sys.exit(1)

    print(f"[+] {len(files)} dosya bulundu, kategori belirleniyor...\n")

    # Kategorize
    plan = []
    by_cat = {cat: 0 for cat in (
        "Gebelik", "Jinekoloji", "Jinekolojik Estetik",
        "Medikal Estetik", "Infertilite", "Paylasim Izinleri")}
    for p in files:
        snippet = read_content_snippet(p)
        parent = p.parent.name if p.parent != folder else ""
        cat, purpose = detect_category(p.name, snippet, parent_dir=parent)
        by_cat[cat] += 1
        plan.append({
            "path": p,
            "filename": p.name,
            "ext": p.suffix.lower().lstrip("."),
            "category": cat,
            "purpose": purpose,
            "size": p.stat().st_size,
            "parent": parent,
        })

    # Plan tablosu
    print(f"{'Dosya':50s} {'Kategori':12s} {'Boyut':>10s}")
    print("-" * 78)
    for item in plan:
        name = item["filename"]
        if len(name) > 48:
            name = name[:46] + ".."
        size_kb = item["size"] / 1024
        print(f"{name:50s} {item['category']:12s} {size_kb:>8.1f}KB")

    print("\nOzet:")
    for cat, count in by_cat.items():
        print(f"  {cat:12s}: {count}")

    if args.dry_run:
        print("\n[DRY-RUN] DB'ye yazma atlandi. Gerçek import icin --dry-run kaldir.")
        return

    # DB'ye yaz
    print(f"\n[+] DB'ye yukleniyor: {args.db}")
    con = sqlite3.connect(args.db)
    cur = con.cursor()
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    inserted = 0
    skipped = 0

    for item in plan:
        try:
            short = item["filename"].rsplit(".", 1)[0]
            base_key = slugify(short) or f"onam_{int(time.time())}"
            key = base_key
            n = 2
            while cur.execute("SELECT 1 FROM consent_forms WHERE form_key=?", (key,)).fetchone():
                key = f"{base_key}_{n}"
                n += 1

            blob = item["path"].read_bytes()
            cur.execute(
                "INSERT INTO consent_forms("
                "form_key, category, short_name, file_name, file_ext, "
                "file_blob, file_size, description, paper_size, added_at, "
                "purpose, is_active, updated_at, created_by"
                ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (key, item["category"], short, item["filename"],
                 item["ext"], blob, item["size"], item["purpose"],
                 "A4", now, item["purpose"], 1, now, "import_script"),
            )
            inserted += 1
        except Exception as ex:
            print(f"  [!] {item['filename']}: {ex}")
            skipped += 1

    con.commit()
    con.close()
    print(f"\n[OK] Import tamamlandi:")
    print(f"  Eklendi: {inserted}")
    print(f"  Atlandi: {skipped}")
    print(f"  DB:      {args.db}")
    print(f"\nSunucuyu yenileyin ve /onam-sablonlari sayfasini acin.")


if __name__ == "__main__":
    main()
