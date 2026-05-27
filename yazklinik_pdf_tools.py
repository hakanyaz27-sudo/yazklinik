"""PDF support-tool integration for YazKlinik D700.

Keeps optional Windows PDF helpers (pdftotext, Stirling-PDF, etc.) behind a
small stdlib-only facade. The main app can keep using PyMuPDF first and fall
back to these tools when a PDF has weak or empty embedded text.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _hidden_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}
    kwargs = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def _support() -> dict[str, str]:
    try:
        from yazklinik_support_paths import support_snapshot

        return support_snapshot()
    except Exception:
        return {}


def _clean_text(text: str) -> str:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def split_pdf_pages(text: str) -> list[dict[str, str | int]]:
    raw = str(text or "")
    if "\f" in raw:
        chunks = raw.split("\f")
    else:
        chunks = [raw]
    pages = []
    for idx, chunk in enumerate(chunks, 1):
        cleaned = _clean_text(chunk)
        if cleaned:
            pages.append({"page": idx, "text": cleaned})
    return pages


def extract_text_pdftotext(pdf_path: str | os.PathLike,
                           max_pages: int | None = None,
                           timeout: float = 25.0) -> dict:
    """Extract text using external pdftotext when available."""
    pdf = Path(pdf_path)
    if not pdf.is_file():
        return {"ok": False, "error": f"PDF bulunamadi: {pdf}"}
    support = _support()
    exe = support.get("pdftotext_exe") or os.environ.get("YAZKLINIK_PDFTOTEXT_EXE")
    if not exe or not Path(exe).is_file():
        return {"ok": False, "error": "pdftotext bulunamadi"}
    cmd = [exe, "-enc", "UTF-8", "-layout"]
    try:
        if max_pages and int(max_pages) > 0:
            cmd.extend(["-f", "1", "-l", str(max(1, int(max_pages)))])
    except Exception:
        pass
    cmd.extend([str(pdf), "-"])
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(pdf.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(timeout),
            **_hidden_subprocess_kwargs(),
        )
    except Exception as ex:
        return {"ok": False, "error": str(ex), "tool": exe}
    text = _clean_text(completed.stdout or "")
    if completed.returncode != 0 and not text:
        return {
            "ok": False,
            "error": (completed.stderr or f"pdftotext exit {completed.returncode}").strip(),
            "tool": exe,
        }
    pages = split_pdf_pages(text)
    return {
        "ok": bool(text),
        "tool": exe,
        "source": "pdftotext",
        "text": text,
        "pages": pages,
        "page_count": len(pages),
        "stderr": (completed.stderr or "").strip()[:500],
    }


def extract_text_pdf_bytes(pdf_bytes: bytes,
                           max_pages: int | None = None,
                           timeout: float = 25.0) -> dict:
    if not pdf_bytes:
        return {"ok": False, "error": "PDF bos"}
    fd = None
    tmp_name = ""
    try:
        fd, tmp_name = tempfile.mkstemp(prefix="yk_pdf_", suffix=".pdf")
        with os.fdopen(fd, "wb") as fh:
            fd = None
            fh.write(pdf_bytes)
        return extract_text_pdftotext(tmp_name, max_pages=max_pages,
                                      timeout=timeout)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass
        if tmp_name:
            try:
                os.remove(tmp_name)
            except Exception:
                pass


def _http_ok(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 500
    except Exception:
        return False


def _process_ids_by_name(names: set[str]) -> set[int]:
    if os.name != "nt":
        return set()
    try:
        out = subprocess.check_output(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process | "
                "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            **_hidden_subprocess_kwargs(),
        )
    except Exception:
        return set()
    import json

    try:
        rows = json.loads(out)
        if isinstance(rows, dict):
            rows = [rows]
    except Exception:
        return set()
    pids = set()
    for row in rows or []:
        name = str(row.get("Name") or "").lower()
        cmd = str(row.get("CommandLine") or "").lower()
        if any(token in name or token in cmd for token in names):
            try:
                pids.add(int(row.get("ProcessId")))
            except Exception:
                pass
    return pids


_PDF_TOOLS_SNAPSHOT_CACHE = {"ts": 0.0, "value": None}


def find_stirling_url(quick: bool = False) -> str:
    configured = os.environ.get("YAZKLINIK_STIRLING_PDF_URL", "").strip()
    timeout = 0.35 if quick else 1.5
    if configured and _http_ok(configured, timeout=timeout):
        return configured.rstrip("/")
    for port in (8080, 8081, 59798):
        url = f"http://127.0.0.1:{port}"
        if _http_ok(url, timeout=timeout):
            return url
    if quick:
        return ""
    if os.name != "nt":
        return ""
    pids = _process_ids_by_name({"stirling", "stirling-pdf"})
    if not pids:
        return ""
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            **_hidden_subprocess_kwargs(),
        )
    except Exception:
        return ""
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        try:
            pid = int(parts[-1])
        except Exception:
            continue
        if pid not in pids or parts[3].upper() != "LISTENING":
            continue
        local = parts[1]
        m = re.search(r":(\d+)$", local)
        if not m:
            continue
        port = int(m.group(1))
        if port < 1024:
            continue
        url = f"http://127.0.0.1:{port}"
        if _http_ok(url):
            return url
    return ""


def pdf_tools_snapshot(force: bool = False, ttl_sec: float = 120.0) -> dict:
    now = __import__("time").time()
    if (
        not force
        and isinstance(_PDF_TOOLS_SNAPSHOT_CACHE.get("value"), dict)
        and now - float(_PDF_TOOLS_SNAPSHOT_CACHE.get("ts") or 0.0) <= ttl_sec
    ):
        return dict(_PDF_TOOLS_SNAPSHOT_CACHE["value"])
    support = _support()
    tools = {
        key: value for key, value in support.items()
        if key in {
            "pdftotext_exe", "pdfinfo_exe", "pdftoppm_exe", "qpdf_exe",
            "wkhtmltopdf_exe", "mutool_exe", "sumatra_pdf_exe",
            "ghostscript_exe", "stirling_pdf_exe", "tesseract_cmd",
            "tessdata",
        }
    }
    snapshot = {
        "ok": bool(tools.get("pdftotext_exe") or tools.get("stirling_pdf_exe")),
        "tools": tools,
        "stirling_url": find_stirling_url(quick=True),
    }
    _PDF_TOOLS_SNAPSHOT_CACHE["ts"] = now
    _PDF_TOOLS_SNAPSHOT_CACHE["value"] = dict(snapshot)
    return snapshot

