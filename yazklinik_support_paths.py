"""Runtime support-tool path bootstrap for YazKlinik D700.

This module is intentionally small and dependency-light. It makes the helper
tools that were downloaded into the D700 package visible to every service
started through ``D500_SERVICE_RUNNER.py``.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _norm(path: str | Path) -> str:
    return str(Path(path)).rstrip("\\/")


def _exists_file(path: str | Path | None) -> Path | None:
    if not path:
        return None
    try:
        p = Path(path)
        return p if p.is_file() else None
    except Exception:
        return None


def _exists_dir(path: str | Path | None) -> Path | None:
    if not path:
        return None
    try:
        p = Path(path)
        return p if p.is_dir() else None
    except Exception:
        return None


def _first_file(candidates) -> Path | None:
    for item in candidates:
        p = _exists_file(item)
        if p:
            return p
    return None


def _prepend_path(directory: str | Path | None) -> None:
    p = _exists_dir(directory)
    if not p:
        return
    current = os.environ.get("PATH", "")
    parts = [x for x in current.split(os.pathsep) if x]
    folded = {_norm(x).lower() for x in parts}
    value = _norm(p)
    if value.lower() not in folded:
        os.environ["PATH"] = value + os.pathsep + current


def _which(name: str) -> Path | None:
    try:
        found = shutil.which(name)
    except BaseException:
        return None
    return Path(found) if found else None


def _project_ffmpeg_bins() -> list[Path]:
    bins: list[Path] = []
    fixed = (
        ROOT
        / "models"
        / "ffmpeg"
        / "extracted"
        / "ffmpeg-n7.1-latest-win64-gpl-shared-7.1"
        / "bin"
    )
    if fixed.is_dir():
        bins.append(fixed)
    ff_root = ROOT / "models" / "ffmpeg"
    if ff_root.is_dir():
        for exe in ff_root.rglob("ffmpeg.exe"):
            bins.append(exe.parent)
    # Preserve order while removing duplicates.
    out: list[Path] = []
    seen: set[str] = set()
    for p in bins:
        key = _norm(p).lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _imageio_ffmpeg_exe() -> Path | None:
    try:
        import imageio_ffmpeg  # type: ignore

        return _exists_file(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return None


def find_ffmpeg_bin() -> Path | None:
    env_bin = _exists_dir(os.environ.get("YAZKLINIK_FFMPEG_BIN"))
    if env_bin and (env_bin / "ffmpeg.exe").is_file():
        return env_bin
    for p in _project_ffmpeg_bins():
        if (p / "ffmpeg.exe").is_file():
            return p
    ffmpeg = _which("ffmpeg.exe") or _which("ffmpeg")
    if ffmpeg:
        return ffmpeg.parent
    imageio_exe = _imageio_ffmpeg_exe()
    if imageio_exe:
        return imageio_exe.parent
    return None


def find_tesseract_cmd() -> Path | None:
    return _first_file(
        [
            os.environ.get("YAZKLINIK_TESSERACT_CMD"),
            os.environ.get("TESSERACT_CMD"),
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            _which("tesseract.exe"),
            _which("tesseract"),
        ]
    )


def find_tessdata_dir(tesseract_cmd: Path | None = None) -> Path | None:
    candidates = []
    if tesseract_cmd:
        candidates.append(tesseract_cmd.parent / "tessdata")
    candidates.extend(
        [
            os.environ.get("YAZKLINIK_TESSDATA_PREFIX"),
            os.environ.get("TESSDATA_PREFIX"),
            ROOT / "tools" / "tesseract" / "tessdata",
        ]
    )
    for item in candidates:
        p = _exists_dir(item)
        if p and (p / "tur.traineddata").is_file():
            return p
    return None


def _project_tool_bins(tool_root_name: str) -> list[Path]:
    roots = [
        ROOT / "tools" / tool_root_name,
        ROOT / "models" / tool_root_name,
    ]
    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for exe in root.rglob("*.exe"):
            key = _norm(exe.parent).lower()
            if key not in seen:
                seen.add(key)
                out.append(exe.parent)
    return out


def _first_tool_exe(env_names: list[str], exe_name: str,
                    extra_candidates: list[str | Path] | None = None) -> Path | None:
    candidates: list[str | Path | None] = [os.environ.get(name) for name in env_names]
    candidates.extend(extra_candidates or [])
    candidates.append(_which(exe_name))
    return _first_file(candidates)


def find_pdftotext_exe() -> Path | None:
    bins = _project_tool_bins("poppler") + _project_tool_bins("xpdf")
    return _first_tool_exe(
        ["YAZKLINIK_PDFTOTEXT_EXE", "PDFTOTEXT_EXE"],
        "pdftotext.exe",
        [*(p / "pdftotext.exe" for p in bins),
         r"C:\Program Files\poppler\Library\bin\pdftotext.exe",
         r"C:\Program Files\poppler\bin\pdftotext.exe",
         r"C:\Program Files\Git\mingw64\bin\pdftotext.exe"],
    )


def find_pdfinfo_exe() -> Path | None:
    bins = _project_tool_bins("poppler") + _project_tool_bins("xpdf")
    return _first_tool_exe(
        ["YAZKLINIK_PDFINFO_EXE", "PDFINFO_EXE"],
        "pdfinfo.exe",
        [*(p / "pdfinfo.exe" for p in bins),
         r"C:\Program Files\poppler\Library\bin\pdfinfo.exe",
         r"C:\Program Files\poppler\bin\pdfinfo.exe",
         r"C:\Program Files\Git\mingw64\bin\pdfinfo.exe"],
    )


def find_pdftoppm_exe() -> Path | None:
    bins = _project_tool_bins("poppler") + _project_tool_bins("xpdf")
    return _first_tool_exe(
        ["YAZKLINIK_PDFTOPPM_EXE", "PDFTOPPM_EXE"],
        "pdftoppm.exe",
        [*(p / "pdftoppm.exe" for p in bins),
         r"C:\Program Files\poppler\Library\bin\pdftoppm.exe",
         r"C:\Program Files\poppler\bin\pdftoppm.exe",
         r"C:\Program Files\Git\mingw64\bin\pdftoppm.exe"],
    )


def find_qpdf_exe() -> Path | None:
    bins = _project_tool_bins("qpdf")
    return _first_tool_exe(
        ["YAZKLINIK_QPDF_EXE", "QPDF_EXE"],
        "qpdf.exe",
        [*(p / "qpdf.exe" for p in bins),
         r"C:\Program Files\qpdf\bin\qpdf.exe"],
    )


def find_wkhtmltopdf_exe() -> Path | None:
    bins = _project_tool_bins("wkhtmltopdf")
    return _first_tool_exe(
        ["YAZKLINIK_WKHTMLTOPDF_EXE", "WKHTMLTOPDF_EXE"],
        "wkhtmltopdf.exe",
        [*(p / "wkhtmltopdf.exe" for p in bins),
         r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
         r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe"],
    )


def find_mutool_exe() -> Path | None:
    bins = _project_tool_bins("mupdf")
    return _first_tool_exe(
        ["YAZKLINIK_MUTOOL_EXE", "MUTOOL_EXE"],
        "mutool.exe",
        [*(p / "mutool.exe" for p in bins),
         r"C:\Program Files\MuPDF\mutool.exe"],
    )


def find_sumatra_pdf_exe() -> Path | None:
    return _first_tool_exe(
        ["YAZKLINIK_SUMATRA_PDF_EXE", "SUMATRA_PDF_EXE"],
        "SumatraPDF.exe",
        [r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
         r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
         Path(os.environ.get("LOCALAPPDATA", "")) / "SumatraPDF" / "SumatraPDF.exe"],
    )


def find_ghostscript_exe() -> Path | None:
    roots = [
        Path(r"C:\Program Files\gs"),
        Path(r"C:\Program Files (x86)\gs"),
        ROOT / "tools" / "ghostscript",
    ]
    candidates: list[Path | str] = []
    for root in roots:
        if root.is_dir():
            candidates.extend(root.glob("**/bin/gswin64c.exe"))
            candidates.extend(root.glob("**/bin/gswin32c.exe"))
    return _first_tool_exe(
        ["YAZKLINIK_GHOSTSCRIPT_EXE", "GHOSTSCRIPT_EXE"],
        "gswin64c.exe",
        candidates,
    )


def find_stirling_pdf_exe() -> Path | None:
    return _first_tool_exe(
        ["YAZKLINIK_STIRLING_PDF_EXE", "STIRLING_PDF_EXE"],
        "stirling-pdf.exe",
        [r"C:\Program Files\Stirling-PDF\stirling-pdf.exe",
         r"C:\Program Files (x86)\Stirling-PDF\stirling-pdf.exe"],
    )


def find_chrome_exe() -> Path | None:
    return _first_file(
        [
            os.environ.get("YAZKLINIK_CHROME_EXE"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            _which("chrome.exe"),
        ]
    )


def find_edge_exe() -> Path | None:
    return _first_file(
        [
            os.environ.get("YAZKLINIK_EDGE_EXE"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            _which("msedge.exe"),
        ]
    )


def find_webview2_exe() -> Path | None:
    direct = _exists_file(os.environ.get("YAZKLINIK_WEBVIEW2_EXE"))
    if direct:
        return direct
    roots = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Microsoft"
        / "EdgeWebView"
        / "Application",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Microsoft"
        / "EdgeWebView"
        / "Application",
    ]
    matches: list[Path] = []
    for root in roots:
        if root.is_dir():
            matches.extend(root.glob("*\\msedgewebview2.exe"))
    if not matches:
        return None
    return sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def apply_support_paths() -> dict[str, str]:
    """Set env vars/PATH for local support tools and return resolved paths."""
    resolved: dict[str, str] = {}

    ffmpeg_bin = find_ffmpeg_bin()
    if ffmpeg_bin:
        _prepend_path(ffmpeg_bin)
        resolved["ffmpeg_bin"] = _norm(ffmpeg_bin)
        os.environ.setdefault("YAZKLINIK_FFMPEG_BIN", resolved["ffmpeg_bin"])
        ffmpeg_exe = ffmpeg_bin / "ffmpeg.exe"
        ffprobe_exe = ffmpeg_bin / "ffprobe.exe"
        if ffmpeg_exe.is_file():
            resolved["ffmpeg_exe"] = str(ffmpeg_exe)
            os.environ.setdefault("FFMPEG_BINARY", str(ffmpeg_exe))
        if ffprobe_exe.is_file():
            resolved["ffprobe_exe"] = str(ffprobe_exe)
            os.environ.setdefault("FFPROBE_BINARY", str(ffprobe_exe))

    tess_cmd = find_tesseract_cmd()
    if tess_cmd:
        _prepend_path(tess_cmd.parent)
        resolved["tesseract_cmd"] = str(tess_cmd)
        os.environ.setdefault("YAZKLINIK_TESSERACT_CMD", str(tess_cmd))
        os.environ.setdefault("TESSERACT_CMD", str(tess_cmd))
    tessdata = find_tessdata_dir(tess_cmd)
    if tessdata:
        resolved["tessdata"] = str(tessdata)
        os.environ.setdefault("YAZKLINIK_TESSDATA_PREFIX", str(tessdata))
        os.environ.setdefault("TESSDATA_PREFIX", str(tessdata))

    pdf_tools = (
        ("pdftotext_exe", "YAZKLINIK_PDFTOTEXT_EXE", find_pdftotext_exe()),
        ("pdfinfo_exe", "YAZKLINIK_PDFINFO_EXE", find_pdfinfo_exe()),
        ("pdftoppm_exe", "YAZKLINIK_PDFTOPPM_EXE", find_pdftoppm_exe()),
        ("qpdf_exe", "YAZKLINIK_QPDF_EXE", find_qpdf_exe()),
        ("wkhtmltopdf_exe", "YAZKLINIK_WKHTMLTOPDF_EXE", find_wkhtmltopdf_exe()),
        ("mutool_exe", "YAZKLINIK_MUTOOL_EXE", find_mutool_exe()),
        ("sumatra_pdf_exe", "YAZKLINIK_SUMATRA_PDF_EXE", find_sumatra_pdf_exe()),
        ("ghostscript_exe", "YAZKLINIK_GHOSTSCRIPT_EXE", find_ghostscript_exe()),
        ("stirling_pdf_exe", "YAZKLINIK_STIRLING_PDF_EXE", find_stirling_pdf_exe()),
    )
    for key, env_name, exe in pdf_tools:
        if exe:
            resolved[key] = str(exe)
            os.environ.setdefault(env_name, str(exe))
            _prepend_path(exe.parent)

    chrome = find_chrome_exe()
    if chrome:
        resolved["chrome_exe"] = str(chrome)
        os.environ.setdefault("YAZKLINIK_CHROME_EXE", str(chrome))
    edge = find_edge_exe()
    if edge:
        resolved["edge_exe"] = str(edge)
        os.environ.setdefault("YAZKLINIK_EDGE_EXE", str(edge))
    webview2 = find_webview2_exe()
    if webview2:
        resolved["webview2_exe"] = str(webview2)
        os.environ.setdefault("YAZKLINIK_WEBVIEW2_EXE", str(webview2))

    return resolved


def support_snapshot() -> dict[str, str]:
    """Return paths without mutating PATH beyond normal apply side effects."""
    return apply_support_paths()

