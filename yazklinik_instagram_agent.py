"""Instagram Hazirlik Ajani.

Hasta USG arsivinden Instagram icin guzel goruntuleri secip
**KVKK ANONIMLESTIRMESI** sonrasi hazir hale getirir.

Akis:
    1. scan_archive(root) -> Aday goruntuler + skor + KVKK uyarisi
    2. anonymize_image(path, opts) -> Ust strip + kose maske + opsiyonel watermark
    3. enhance_image(path, opts) -> Netlik, kontrast, parlaklik, doygunluk
    4. export_draft(path, format) -> Instagram boyutunda (1:1 / 4:5 / 1.91:1)
                                      'instagram_drafts/' klasorune YAZ
    5. caption_templates(...) -> Egitim/farkindalik metni + hashtag sozlugu

KVKK / Etik kurallar:
    - HASTA KIMLIGI iceren USG basligi VARSAYILAN OLARAK KIRPILIR
    - Doktor onayi olmadan hicbir resim "Instagram hazir" isaretlenmez
    - Hicbir resim Instagram'a otomatik gonderilmez - sadece DRAFT klasore yazilir
    - Orijinal NAS dosyasi ASLA degistirilmez veya silinmez (read-only)
    - Watermark opsiyonel; doktor isterse "© Op. Dr. Hakan Yaz" eklenir

Bagimlilik: stdlib + Pillow (PIL) + numpy + opsiyonel fitz (PDF icin).
PIL/numpy yoksa skor sadece dosya boyutu/mtime'a duser; iyilestirme calismaz.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


AGENT_VERSION = "2026.05.16-instagram"
SOURCE_LABEL = "USG arsivi -> Instagram draft"

# Desteklenen uzantilar
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif")
PDF_EXTS = (".pdf",)

# Instagram boyut presetleri (genislik x yukseklik)
IG_PRESETS = {
    "square": (1080, 1080),       # 1:1 - klasik feed
    "portrait": (1080, 1350),     # 4:5 - feed onerilen
    "landscape": (1080, 566),     # 1.91:1 - link card / story landscape
    "story": (1080, 1920),        # 9:16 - story / reel
}

# Anonim ust strip orani (USG cihazinin uste yazdigi hasta bilgi seridi)
DEFAULT_HEADER_CROP_RATIO = 0.13  # ust %13
DEFAULT_SIDE_CROP_RATIO = 0.0     # yan kirpma kapali

# Skor agirliklari
SCORE_WEIGHTS = {
    "sharpness": 0.30,
    "resolution": 0.20,
    "aspect_fit": 0.15,
    "recency": 0.15,
    "file_size": 0.10,
    "filename_hint": 0.10,
}

# Dosya adi ipuclari (4D/HD/MD genelde daha gosterisli kareler)
FILENAME_GOOD_HINTS = ("4d", "hd", "md", "5d", "render", "face", "profile",
                       "yuz", "el", "ayak", "kalp")
FILENAME_BAD_HINTS = ("doppler", "spectrum", "trace", "measure", "olcum",
                       "report", "rapor")


# --- Opsiyonel modulleri tembel import et ---

def _try_pil():
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw, ImageFont  # noqa: F401
        return True
    except Exception:
        return False


def _try_numpy():
    try:
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def _try_fitz():
    try:
        import fitz  # noqa: F401
        return True
    except Exception:
        return False


HAS_PIL = _try_pil()
HAS_NUMPY = _try_numpy()
HAS_FITZ = _try_fitz()


@dataclass
class ImageCandidate:
    path: str
    filename: str
    patient_folder: str            # ornek: "F123_Ayse_Yilmaz"
    visit_date_str: str            # ornek: "20260415"
    size_bytes: int
    modified_at: str
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[float] = None
    is_pdf: bool = False
    pdf_page_count: int = 0
    sharpness_score: Optional[float] = None   # ham Laplacian variance
    final_score: float = 0.0
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)
    kvkk_warning: str = ""


@dataclass
class EnhanceOptions:
    header_crop_ratio: float = DEFAULT_HEADER_CROP_RATIO
    side_crop_ratio: float = DEFAULT_SIDE_CROP_RATIO
    sharpen: float = 1.2          # 0.0 = kapali, 1.0 = soft, 2.0 = guclu
    contrast: float = 1.10        # 1.0 = degisme
    brightness: float = 1.05
    saturation: float = 1.05
    add_watermark: bool = True
    watermark_text: str = "(c) Op. Dr. Hakan Yaz"
    output_format: str = "portrait"  # IG_PRESETS anahtari veya 'original'
    blur_corners: bool = False    # alt kose hasta bilgisi olabilir
    output_quality: int = 92      # JPEG kalite


@dataclass
class EnhanceResult:
    source_path: str
    draft_path: str
    width: int
    height: int
    format: str
    size_bytes: int
    requires_doctor_review: bool = True
    notes: str = ""
    agent_version: str = AGENT_VERSION


# --- Yol guvenligi ---

def _resolve_inside(root: str, candidate: str) -> Optional[Path]:
    """Path traversal koruma: candidate mutlaka root altinda olmali."""
    try:
        root_p = Path(root).resolve()
        cand_p = Path(candidate).resolve()
        cand_p.relative_to(root_p)
        return cand_p
    except Exception:
        return None


def _safe_folder_name(name: str) -> str:
    out = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "").strip())
    return out[:80] or "patient"


# --- Tarama + skorlama ---

def _walk_files(root: Path, include_pdf: bool, max_files: int = 5000):
    seen = 0
    for dp, dn, fn in os.walk(root):
        # Cok derin / cop klasorleri atla
        if "__pycache__" in dp or ".git" in dp:
            continue
        for f in fn:
            ext = os.path.splitext(f)[1].lower()
            if ext in IMAGE_EXTS or (include_pdf and ext in PDF_EXTS):
                yield Path(dp) / f
                seen += 1
                if seen >= max_files:
                    return


def _extract_visit_date(path: Path) -> str:
    # Voluson tipik: ROOT/Hastalar/F123_Ad_Soyad/YYYYMMDD/IMG_*.ext
    for part in path.parts:
        if re.fullmatch(r"\d{8}", part):
            return part
    return ""


def _extract_patient_folder(path: Path) -> str:
    for part in path.parts:
        if re.match(r"^[Ff]\d+_", part) or re.search(r"_\d{2,}_", part):
            return part
    # Hastalar/<folder>/... varsa
    parts = path.parts
    for i, p in enumerate(parts):
        if p.lower() == "hastalar" and i + 1 < len(parts):
            return parts[i + 1]
    return parts[-3] if len(parts) >= 3 else ""


def _laplacian_variance(pil_img) -> Optional[float]:
    """PIL + numpy ile Laplacian variance - netlik metrigi."""
    if not (HAS_PIL and HAS_NUMPY):
        return None
    try:
        import numpy as np
        gray = pil_img.convert("L")
        arr = np.asarray(gray, dtype=np.float32)
        # Manuel 3x3 Laplacian (komsulardan center sapmasi)
        h, w = arr.shape
        if h < 8 or w < 8:
            return None
        # Hizli yaklasim: diff'ler arasi karelerin ortalamasi
        dx = arr[:, 1:] - arr[:, :-1]
        dy = arr[1:, :] - arr[:-1, :]
        return float(dx.var() + dy.var())
    except Exception:
        return None


def _open_image(path: Path):
    """JPG/PNG dosyasi PIL Image dondur. PDF ise ilk sayfayi raster yap."""
    if not HAS_PIL:
        return None
    try:
        from PIL import Image
        ext = path.suffix.lower()
        if ext in IMAGE_EXTS:
            img = Image.open(str(path))
            img.load()
            return img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img
        if ext in PDF_EXTS and HAS_FITZ:
            import fitz
            doc = fitz.open(str(path))
            if doc.page_count == 0:
                return None
            page = doc.load_page(0)
            mat = fitz.Matrix(2.0, 2.0)  # 2x DPI
            pix = page.get_pixmap(matrix=mat, alpha=False)
            from io import BytesIO
            img = Image.open(BytesIO(pix.tobytes("png")))
            img.load()
            return img.convert("RGB")
    except Exception:
        return None
    return None


def _score_candidate(c: ImageCandidate, now: datetime) -> ImageCandidate:
    """0..1 araliginda nihai skor + breakdown."""
    breakdown: Dict[str, float] = {}

    # 1. Sharpness (Laplacian variance normalize)
    sharp = 0.0
    if c.sharpness_score is not None:
        # Tipik tatminkar USG 100-600 araliginda; >800 cok keskin
        sharp = max(0.0, min(1.0, (c.sharpness_score - 50) / 750.0))
    breakdown["sharpness"] = sharp

    # 2. Resolution
    res = 0.0
    if c.width and c.height:
        mp = (c.width * c.height) / 1_000_000.0
        res = max(0.0, min(1.0, mp / 3.0))  # 3 MP+ tam puan
    breakdown["resolution"] = res

    # 3. Aspect fit (1:1 ideal, 4:5 cok iyi, kare degil olcumler dusuk)
    af = 0.0
    if c.aspect_ratio:
        ideal = [(1.0, 1.0), (0.8, 0.9), (1.91, 0.85)]
        af = max(0.5 - min(abs(c.aspect_ratio - t[0]) / 2, 0.5) + t[1] * 0.5 for t in ideal)
        af = max(0.0, min(1.0, af))
    breakdown["aspect_fit"] = af

    # 4. Recency
    rec = 0.0
    try:
        mt = datetime.fromisoformat(c.modified_at)
        days = (now - mt).days
        if days < 0:
            days = 0
        rec = max(0.0, 1.0 - (days / 365.0))  # 1 yil sonra 0
    except Exception:
        pass
    breakdown["recency"] = rec

    # 5. File size (proxy for quality)
    fs = 0.0
    if c.size_bytes > 0:
        kb = c.size_bytes / 1024.0
        fs = max(0.0, min(1.0, (kb - 80) / 1500.0))  # 80KB-1.5MB sweet spot
    breakdown["file_size"] = fs

    # 6. Filename hints
    fh = 0.5
    name_low = c.filename.lower()
    if any(h in name_low for h in FILENAME_GOOD_HINTS):
        fh += 0.4
    if any(h in name_low for h in FILENAME_BAD_HINTS):
        fh -= 0.4
    fh = max(0.0, min(1.0, fh))
    breakdown["filename_hint"] = fh

    final = sum(breakdown[k] * w for k, w in SCORE_WEIGHTS.items())
    c.final_score = round(max(0.0, min(1.0, final)), 4)
    c.score_breakdown = {k: round(v, 3) for k, v in breakdown.items()}
    return c


def scan_archive(root: str, max_candidates: int = 60, include_pdf: bool = True,
                 min_score: float = 0.30) -> Dict[str, Any]:
    """NAS ya da herhangi bir klasoru tara, en yuksek skorlu adaylari dondur.

    Hicbir dosya yazmaz/degistirmez.
    """
    root_path = Path(root)
    started = datetime.now()
    result: Dict[str, Any] = {
        "ok": False,
        "root": str(root_path),
        "scanned_count": 0,
        "candidates": [],
        "skipped_reasons": {},
        "has_pil": HAS_PIL,
        "has_numpy": HAS_NUMPY,
        "has_fitz": HAS_FITZ,
        "started_at": started.isoformat(timespec="seconds"),
        "agent_version": AGENT_VERSION,
    }

    if not root_path.exists():
        result["error"] = f"Klasor bulunamadi: {root_path}"
        return result

    candidates: List[ImageCandidate] = []
    skipped: Dict[str, int] = {}

    for path in _walk_files(root_path, include_pdf=include_pdf):
        result["scanned_count"] += 1
        try:
            st = path.stat()
        except (OSError, PermissionError):
            skipped["stat_fail"] = skipped.get("stat_fail", 0) + 1
            continue

        c = ImageCandidate(
            path=str(path),
            filename=path.name,
            patient_folder=_extract_patient_folder(path),
            visit_date_str=_extract_visit_date(path),
            size_bytes=int(st.st_size),
            modified_at=datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            is_pdf=path.suffix.lower() in PDF_EXTS,
        )

        # Cok kucuk dosyalar (thumb veya bozuk) at
        if c.size_bytes < 30 * 1024:
            skipped["too_small"] = skipped.get("too_small", 0) + 1
            continue

        # Image meta + sharpness
        img = _open_image(path)
        if img is None:
            if not c.is_pdf:
                skipped["open_fail"] = skipped.get("open_fail", 0) + 1
                continue
            # PDF acilamadi - sadece dosya boyutu/mtime ile skor
        else:
            c.width, c.height = img.size
            c.aspect_ratio = round(c.width / c.height, 3) if c.height else None
            c.sharpness_score = _laplacian_variance(img)
            if c.is_pdf:
                try:
                    import fitz
                    doc = fitz.open(str(path))
                    c.pdf_page_count = doc.page_count
                except Exception:
                    pass

        c = _score_candidate(c, datetime.now())

        # KVKK uyarisi her zaman:
        c.kvkk_warning = (
            "KVKK: USG basliginda hasta adi / TC / tarih olabilir. "
            "Anonimlestirmeden Instagram'a yuklemeyin."
        )
        if c.width and c.height and c.width / max(c.height, 1) > 1.5:
            c.flags.append("genis_aspect_hasta_bilgi_alani_riski")

        if c.final_score >= min_score:
            candidates.append(c)
        else:
            skipped["low_score"] = skipped.get("low_score", 0) + 1

    candidates.sort(key=lambda x: x.final_score, reverse=True)
    candidates = candidates[:max_candidates]

    result["ok"] = True
    result["candidates"] = [asdict(c) for c in candidates]
    result["skipped_reasons"] = skipped
    result["finished_at"] = datetime.now().isoformat(timespec="seconds")
    result["count_returned"] = len(candidates)
    return result


# --- Anonimlestirme + iyilestirme ---

def _ensure_pil():
    if not HAS_PIL:
        raise RuntimeError("Pillow yuklu degil. pip install Pillow")


def _apply_crop(img, header_ratio: float, side_ratio: float):
    """Ust strip + iki yan strip kirp."""
    w, h = img.size
    top = int(h * max(0.0, min(0.45, header_ratio)))
    side = int(w * max(0.0, min(0.30, side_ratio)))
    box = (side, top, max(side + 1, w - side), max(top + 1, h))
    return img.crop(box)


def _apply_corner_blur(img, ratio: float = 0.20):
    """Alt iki kosede kucuk dikdortgeni bulaniklastir (hasta bilgisi olabilir)."""
    from PIL import ImageFilter
    w, h = img.size
    cw = int(w * ratio)
    ch = int(h * 0.10)
    for box in [(0, h - ch, cw, h), (w - cw, h - ch, w, h)]:
        try:
            piece = img.crop(box).filter(ImageFilter.GaussianBlur(radius=12))
            img.paste(piece, box)
        except Exception:
            pass
    return img


def _apply_enhance(img, opts: EnhanceOptions):
    from PIL import ImageEnhance, ImageFilter
    if opts.sharpen and opts.sharpen > 0:
        amt = max(0.0, min(3.0, float(opts.sharpen)))
        radius = 1.2 + amt * 0.6
        percent = int(60 + amt * 80)
        img = img.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=2))
    if opts.contrast and abs(opts.contrast - 1.0) > 0.01:
        img = ImageEnhance.Contrast(img).enhance(float(opts.contrast))
    if opts.brightness and abs(opts.brightness - 1.0) > 0.01:
        img = ImageEnhance.Brightness(img).enhance(float(opts.brightness))
    if opts.saturation and abs(opts.saturation - 1.0) > 0.01:
        img = ImageEnhance.Color(img).enhance(float(opts.saturation))
    return img


def _fit_format(img, fmt_key: str):
    if fmt_key == "original" or fmt_key not in IG_PRESETS:
        return img
    target_w, target_h = IG_PRESETS[fmt_key]
    return _center_fit(img, target_w, target_h)


def _center_fit(img, target_w: int, target_h: int):
    """Hedef oran disinda kalan kismi kirp, sonra hedef boyuta yeniden boyutlandir."""
    w, h = img.size
    target_aspect = target_w / target_h
    src_aspect = w / max(h, 1)
    if src_aspect > target_aspect:
        # daha genis - sol/sag kirp
        new_w = int(h * target_aspect)
        x = (w - new_w) // 2
        img = img.crop((x, 0, x + new_w, h))
    elif src_aspect < target_aspect:
        # daha uzun - ust/alt kirp
        new_h = int(w / target_aspect)
        y = (h - new_h) // 3   # alttan biraz daha kirp (alt strip bilgi olabilir)
        img = img.crop((0, y, w, y + new_h))
    from PIL import Image
    return img.resize((target_w, target_h), Image.LANCZOS)


def _draw_watermark(img, text: str):
    from PIL import ImageDraw, ImageFont
    w, h = img.size
    pad = max(10, int(min(w, h) * 0.015))
    font_size = max(14, int(min(w, h) * 0.022))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = font_size * len(text) // 2, font_size
    x = w - tw - pad
    y = h - th - pad
    # Yari saydam zemin
    draw.rectangle([x - 6, y - 4, x + tw + 6, y + th + 4],
                   fill=(0, 0, 0, 120))
    draw.text((x, y), text, fill=(255, 255, 255), font=font)
    return img


def enhance_image(source_path: str, output_dir: str, opts: EnhanceOptions,
                  allowed_root: Optional[str] = None) -> EnhanceResult:
    """Anonimlestirme + iyilestirme + format + watermark uygula, draft'a yaz.
    Orijinal dosyaya HIC DOKUNULMAZ.
    """
    _ensure_pil()
    src = Path(source_path)
    if allowed_root:
        if not _resolve_inside(allowed_root, source_path):
            raise PermissionError(f"Kaynak izinli root disinda: {source_path}")
    if not src.is_file():
        raise FileNotFoundError(str(src))

    img = _open_image(src)
    if img is None:
        raise RuntimeError(f"Goruntu acilamadi: {src}")
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    # 1. Anonimlestir
    img = _apply_crop(img, opts.header_crop_ratio, opts.side_crop_ratio)
    if opts.blur_corners:
        img = _apply_corner_blur(img)

    # 2. Iyilestir
    img = _apply_enhance(img, opts)

    # 3. Format
    img = _fit_format(img, opts.output_format)

    # 4. Watermark
    if opts.add_watermark and opts.watermark_text:
        img = _draw_watermark(img, opts.watermark_text)

    # 5. Yaz
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = hashlib.md5(str(src).encode("utf-8")).hexdigest()[:10]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fmt = opts.output_format if opts.output_format in IG_PRESETS else "original"
    fname = f"ig_{ts}_{fmt}_{stem}.jpg"
    out_path = out_dir / fname
    img.save(str(out_path), "JPEG", quality=int(opts.output_quality), optimize=True)

    return EnhanceResult(
        source_path=str(src),
        draft_path=str(out_path),
        width=img.size[0],
        height=img.size[1],
        format=fmt,
        size_bytes=out_path.stat().st_size,
        notes="Draft hazir. Yine de gozle son kontrol yapin.",
    )


# --- Caption + hashtag ---

CAPTION_TEMPLATES = {
    "egitim_3d_4d": [
        "3D/4D ultrason ile bebeginizin yuz hatlarini detayli gorebilirsiniz."
        " Egitim icin paylasildi.\n\nRandevu ve detayli bilgi: profilde."
        " #ultrason #3dusg #gebelik",
        "Ucuncu trimesterde fetal yuz gorunumu. Genellikle 28-32. haftada"
        " en net sonuc alinir.\n\nKontrolleriniz icin: klinik linki profilde.",
    ],
    "gebelik_takip": [
        "Saglikli gebelik takibi icin duzenli kontrol onemlidir."
        " Hatirlatma: ilk trimester taramasi 11-14 hafta arasi.\n\n"
        " #gebelik #anneadayi #kadindogum",
        "Detayli ultrasonografi 18-22. haftada yapilir."
        " Fetal anatominin detayli incelenmesi icin ideal donemdir.",
    ],
    "kontrol_hatirlatma": [
        "Yillik jinekolojik kontrol kadin sagligi icin onemli."
        " Pap smear, USG ve klinik muayene rutin takibinizi planlayin.",
        "Smear takibi ve HPV testi sayesinde erken tani mumkun."
        " Randevu icin profilde iletisim bilgileri.",
    ],
    "farkindalik": [
        "Erken tani hayat kurtarir. Kadin sagliginda duzenli kontrol sart."
        " #kadinsagligi #erkenTani",
        "Saglikli yasam, saglikli gebelik. Kontrole gelmek erteleyici degil,"
        " yatirimdir.",
    ],
}

HASHTAG_GROUPS = {
    "core_tr": [
        "#kadındoğum", "#kadinsagligi", "#gebelik", "#ultrason",
        "#usg", "#anneadayi", "#hamilelik", "#jinekoloji",
        "#kontrolezaman", "#sağlık",
    ],
    "obgyn_intl": [
        "#obgyn", "#obstetrics", "#gynecology", "#ultrasound",
        "#pregnancy", "#prenatal", "#womenshealth", "#maternalhealth",
    ],
    "brand": [
        "#yazklinik", "#drhakanyaz", "#opdrhakanyaz",
    ],
    "specialty_3d4d": [
        "#3dusg", "#4dusg", "#hdusg", "#fetalyuz", "#bebek",
    ],
    "ivf_ovulasyon": [
        "#tupbebek", "#ivf", "#ovulasyon", "#kisirlik", "#yumurtlama",
    ],
}


@dataclass
class CaptionSuggestion:
    template_key: str
    text: str
    hashtags: List[str]
    char_count: int
    agent_version: str = AGENT_VERSION


def caption_suggestions(theme: str = "egitim_3d_4d",
                        hashtag_groups: Optional[List[str]] = None,
                        custom_intro: str = "") -> List[CaptionSuggestion]:
    theme_key = theme if theme in CAPTION_TEMPLATES else "egitim_3d_4d"
    groups = hashtag_groups or ["core_tr", "brand"]
    tags: List[str] = []
    for g in groups:
        tags.extend(HASHTAG_GROUPS.get(g, []))
    seen = set(); tags = [t for t in tags if not (t in seen or seen.add(t))]
    tags = tags[:30]  # Instagram 30 hashtag siniri

    out: List[CaptionSuggestion] = []
    for body in CAPTION_TEMPLATES[theme_key]:
        text = (custom_intro + "\n\n" + body).strip() if custom_intro else body
        out.append(CaptionSuggestion(
            template_key=theme_key,
            text=text,
            hashtags=tags,
            char_count=len(text) + sum(len(t) + 1 for t in tags),
        ))
    return out


# --- KVKK kontrol listesi ---

KVKK_CHECKLIST = [
    "Goruntu basligindaki hasta adi ve TC kimligi tamamen kapatildi mi?",
    "Tarih bilgisi gunluk hayata isaret edip hastanin kim oldugunu ifsa etmiyor mu?",
    "USG cihaz seri numarasi / dosya numarasi anonim mi?",
    "Hasta veya yakini paylasim icin yazili onay verdi mi?",
    "Goruntu klinik vaka olmaktan cikip educational/awareness icerigine donustu mu?",
    "Yorum/altyazi ile hasta tahmin edilebilir hale gelmiyor mu?",
    "Brans dernegi etik kurallari (TJOD) ile uyumlu mu?",
]


def kvkk_compliance_review(candidate_paths: List[str]) -> Dict[str, Any]:
    """Doktor onayi oncesi her bir aday icin kontrol listesi dondurur."""
    return {
        "ok": True,
        "checklist": list(KVKK_CHECKLIST),
        "per_candidate": [
            {
                "path": p,
                "requires_acknowledgment": True,
                "acknowledged": False,
            } for p in candidate_paths
        ],
        "note": "Doktor her bir maddeyi onaylamadan 'export' yapilmamali.",
        "agent_version": AGENT_VERSION,
    }


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    print("HAS_PIL=", HAS_PIL, "HAS_NUMPY=", HAS_NUMPY, "HAS_FITZ=", HAS_FITZ)
    result = scan_archive(root, max_candidates=10, include_pdf=True)
    print(f"Scanned: {result['scanned_count']}  Candidates: {len(result['candidates'])}  Skipped: {result['skipped_reasons']}")
    for c in result["candidates"][:10]:
        print(f"  [{c['final_score']:.2f}] {c['filename']:40} ({c.get('width')}x{c.get('height')}) {c.get('size_bytes')}B  {c.get('kvkk_warning','')[:60]}")
    print("\n--- Caption ornegi ---")
    for s in caption_suggestions("egitim_3d_4d", ["core_tr", "specialty_3d4d", "brand"]):
        print(f"\n{s.text}\n[hashtags] {' '.join(s.hashtags[:10])}...")
