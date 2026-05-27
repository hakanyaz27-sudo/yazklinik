"""Gama Tip laboratuvar sonucu ajani.

Amac:
- Gama Tip tetkik portalindan sonuc dosyalarini kontrollu almak.
- Hasta adina gore YazKlinik hastasi ile eslestirmek.
- Eslesme guvenli degilse otomatik yuklememek.

Portal bilgileri config.env veya ortam degiskenlerinden okunur:
- GAMA_LAB_PORTAL_URL
- GAMA_LAB_USERNAME
- GAMA_LAB_PASSWORD
- GAMA_LAB_RESULTS_URL
- GAMA_LAB_ROW_SELECTOR
- GAMA_LAB_NAME_SELECTOR
- GAMA_LAB_DATE_SELECTOR
- GAMA_LAB_DOWNLOAD_SELECTOR
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from yazklinik_db_adapter import agent_connection as _pgconn  # PG-primary aware (cutover)
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.19-gama-lab-agent"


@dataclass
class GamaLabResult:
    patient_name: str
    result_date: str
    file_path: str
    source: str = "gama-tip"
    raw_text: str = ""
    patient_key: str = ""
    match_score: float = 0.0
    status: str = "pending"
    meta_json: str = "{}"


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _state_dir() -> Path:
    p = _project_root() / "runtime_state" / "gama_lab"
    p.mkdir(parents=True, exist_ok=True)
    (p / "inbox").mkdir(parents=True, exist_ok=True)
    return p


def _config_env_path() -> Path:
    return _project_root() / "config.env"


def _read_config_env() -> Dict[str, str]:
    out: Dict[str, str] = {}
    p = _config_env_path()
    if not p.exists():
        return out
    try:
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return out


def _cfg(key: str, default: str = "") -> str:
    if os.environ.get(key):
        return str(os.environ.get(key) or "").strip()
    return str(_read_config_env().get(key, default) or "").strip()


def db_path() -> str:
    return (_cfg("YAZKLINIK_DB_PATH")
            or str(_project_root() / "local_db" / "yazklinik_v68.sqlite3"))


def load_config() -> Dict[str, Any]:
    return {
        "portal_url": _cfg("GAMA_LAB_PORTAL_URL"),
        "username": _cfg("GAMA_LAB_USERNAME"),
        "password_set": bool(_cfg("GAMA_LAB_PASSWORD")),
        "results_url": _cfg("GAMA_LAB_RESULTS_URL"),
        "row_selector": _cfg("GAMA_LAB_ROW_SELECTOR", "table tbody tr"),
        "name_selector": _cfg("GAMA_LAB_NAME_SELECTOR"),
        "date_selector": _cfg("GAMA_LAB_DATE_SELECTOR"),
        "download_selector": _cfg("GAMA_LAB_DOWNLOAD_SELECTOR", "a[href]"),
    }


def ensure_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS gama_lab_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT,
            result_date TEXT,
            file_path TEXT,
            source TEXT,
            raw_text TEXT,
            patient_key TEXT,
            match_score REAL,
            status TEXT,
            meta_json TEXT,
            created_at TEXT,
            imported_at TEXT,
            whatsapp_at TEXT
        )
    """)
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_gama_lab_status "
        "ON gama_lab_results(status, patient_key, result_date)")


def normalize_text(value: str) -> str:
    text = str(value or "").strip().lower()
    repl = {
        "ı": "i", "İ": "i", "ğ": "g", "Ğ": "g",
        "ü": "u", "Ü": "u", "ş": "s", "Ş": "s",
        "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    }
    for src, dst in repl.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _token_score(query: str, candidate: str) -> float:
    q = normalize_text(query)
    c = normalize_text(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    q_tokens = set(q.split())
    c_tokens = set(c.split())
    if not q_tokens or not c_tokens:
        return 0.0
    inter = len(q_tokens & c_tokens)
    score = inter / max(len(q_tokens), len(c_tokens))
    if q in c or c in q:
        score = max(score, 0.82)
    return round(float(score), 3)


def find_patient_by_name(patient_name: str, database_path: Optional[str] = None) -> Dict[str, Any]:
    database_path = database_path or db_path()
    best: Dict[str, Any] = {"patient_key": "", "display_name": "", "score": 0.0}
    if not patient_name:
        return best
    con = _pgconn(sqlite_path=database_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT folder_key, COALESCE(NULLIF(display_name,''), folder_key) AS display_name "
            "FROM patients WHERE COALESCE(archived_at, '') = '' LIMIT 20000"
        ).fetchall()
    finally:
        con.close()
    for row in rows:
        score = max(
            _token_score(patient_name, row["display_name"]),
            _token_score(patient_name, row["folder_key"]),
        )
        if score > float(best.get("score") or 0):
            best = {
                "patient_key": row["folder_key"],
                "display_name": row["display_name"],
                "score": score,
            }
    return best


def register_pending_result(result: GamaLabResult, database_path: Optional[str] = None) -> int:
    database_path = database_path or db_path()
    match = find_patient_by_name(result.patient_name, database_path)
    if match.get("score", 0) >= 0.82:
        result.patient_key = str(match.get("patient_key") or "")
        result.match_score = float(match.get("score") or 0)
        result.status = "matched"
    else:
        result.patient_key = ""
        result.match_score = float(match.get("score") or 0)
        result.status = "unmatched"
    con = _pgconn(sqlite_path=database_path)
    try:
        ensure_schema(con)
        cur = con.execute(
            "INSERT INTO gama_lab_results("
            "patient_name, result_date, file_path, source, raw_text, patient_key, "
            "match_score, status, meta_json, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (result.patient_name, result.result_date, result.file_path,
             result.source, result.raw_text, result.patient_key,
             result.match_score, result.status, result.meta_json,
             datetime.now().isoformat(sep=" ", timespec="seconds")))
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def add_manual_file(patient_name: str, result_date: str, source_path: str,
                    raw_text: str = "", meta: Optional[Dict[str, Any]] = None) -> int:
    src = Path(source_path)
    inbox = _state_dir() / "inbox"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "_", src.name or "sonuc")
    dest = inbox / f"{stamp}_{safe_name}"
    if src.exists() and src.is_file() and src.resolve() != dest.resolve():
        shutil.copy2(str(src), str(dest))
    result = GamaLabResult(
        patient_name=patient_name,
        result_date=result_date or datetime.now().strftime("%Y-%m-%d"),
        file_path=str(dest if dest.exists() else src),
        raw_text=raw_text or "",
        meta_json=json.dumps(meta or {}, ensure_ascii=False),
    )
    return register_pending_result(result)


def list_results(status: str = "", limit: int = 100,
                 database_path: Optional[str] = None) -> List[Dict[str, Any]]:
    database_path = database_path or db_path()
    con = _pgconn(sqlite_path=database_path)
    con.row_factory = sqlite3.Row
    try:
        ensure_schema(con)
        if status:
            rows = con.execute(
                "SELECT * FROM gama_lab_results WHERE status=? "
                "ORDER BY id DESC LIMIT ?",
                (status, int(limit))).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM gama_lab_results ORDER BY id DESC LIMIT ?",
                (int(limit),)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def update_status(result_id: int, status: str, database_path: Optional[str] = None) -> None:
    database_path = database_path or db_path()
    field = "imported_at" if status == "imported" else "whatsapp_at" if status == "whatsapp" else None
    con = _pgconn(sqlite_path=database_path)
    try:
        ensure_schema(con)
        if field:
            con.execute(
                f"UPDATE gama_lab_results SET status=?, {field}=? WHERE id=?",
                (status, datetime.now().isoformat(sep=" ", timespec="seconds"), result_id))
        else:
            con.execute("UPDATE gama_lab_results SET status=? WHERE id=?", (status, result_id))
        con.commit()
    finally:
        con.close()


def health_check() -> Dict[str, Any]:
    cfg = load_config()
    return {
        "ok": True,
        "agent_version": AGENT_VERSION,
        "configured": bool(cfg.get("portal_url") and cfg.get("username") and cfg.get("password_set")),
        "config": {k: v for k, v in cfg.items() if k != "password_set"},
        "password_set": cfg.get("password_set"),
        "pending_count": len(list_results(limit=500)),
    }


def sync_from_portal(dry_run: bool = False) -> Dict[str, Any]:
    cfg = load_config()
    if not (cfg.get("portal_url") and cfg.get("username") and cfg.get("password_set")):
        return {
            "ok": False,
            "needs_config": True,
            "message": "GAMA_LAB_PORTAL_URL, GAMA_LAB_USERNAME ve GAMA_LAB_PASSWORD gerekli.",
        }
    try:
        from playwright.sync_api import sync_playwright
    except Exception as ex:
        return {"ok": False, "needs_playwright": True, "message": f"playwright yuklu degil: {ex}"}

    saved = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
        page = browser.new_page(ignore_https_errors=True)
        try:
            page.goto(cfg["portal_url"], wait_until="domcontentloaded", timeout=45000)
            for selector in ('input[name="username"]', 'input[name="user"]', '#username', '#UserName', 'input[type="text"]'):
                if page.locator(selector).count():
                    page.locator(selector).first.fill(cfg["username"])
                    break
            for selector in ('input[name="password"]', '#password', '#Password', 'input[type="password"]'):
                if page.locator(selector).count():
                    page.locator(selector).first.fill(_cfg("GAMA_LAB_PASSWORD"))
                    break
            for selector in ('button[type="submit"]', 'input[type="submit"]', 'button:has-text("Giriş")', 'button:has-text("Login")'):
                if page.locator(selector).count():
                    page.locator(selector).first.click()
                    break
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            if cfg.get("results_url"):
                page.goto(cfg["results_url"], wait_until="domcontentloaded", timeout=45000)
            rows = page.locator(cfg.get("row_selector") or "table tbody tr")
            total = min(rows.count(), 80)
            for idx in range(total):
                row = rows.nth(idx)
                row_text = row.inner_text(timeout=5000)
                if not row_text.strip():
                    continue
                name = ""
                if cfg.get("name_selector") and row.locator(cfg["name_selector"]).count():
                    name = row.locator(cfg["name_selector"]).first.inner_text(timeout=3000)
                if not name:
                    name = row_text.splitlines()[0][:120]
                date_text = datetime.now().strftime("%Y-%m-%d")
                if cfg.get("date_selector") and row.locator(cfg["date_selector"]).count():
                    date_text = row.locator(cfg["date_selector"]).first.inner_text(timeout=3000)[:20]
                file_path = ""
                link = row.locator(cfg.get("download_selector") or "a[href]").first
                if link.count() and not dry_run:
                    with page.expect_download(timeout=20000) as dlinfo:
                        link.click()
                    download = dlinfo.value
                    safe = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "_", download.suggested_filename or f"gama_{idx}.pdf")
                    dest = _state_dir() / "inbox" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe}"
                    download.save_as(str(dest))
                    file_path = str(dest)
                if file_path:
                    rid = register_pending_result(GamaLabResult(
                        patient_name=name,
                        result_date=date_text,
                        file_path=file_path,
                        raw_text=row_text,
                        meta_json=json.dumps({"portal_row": idx}, ensure_ascii=False),
                    ))
                    saved.append({"id": rid, "patient_name": name})
        finally:
            browser.close()
    return {"ok": True, "dry_run": dry_run, "saved": saved, "saved_count": len(saved)}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
