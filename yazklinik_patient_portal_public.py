"""Standalone public patient portal for YazKlinik D700.

This process intentionally does not import ``yazklinik_web.py``.  It exposes
only token-based patient portal pages and media endpoints, so a public patient
hostname cannot reach the doctor's admin/login surface through this app.
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import mimetypes
import os
import re
import sqlite3
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from flask import Flask, abort, make_response, redirect, request, send_file


ROOT = Path(__file__).resolve().parent
CONFIG_ENV = ROOT / "config.env"
TOKEN_RE = re.compile(r"^[a-fA-F0-9]{24,80}$")
MEDIA_EXTS = {
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".webp": "image",
    ".gif": "image",
    ".pdf": "pdf",
    ".mp4": "video",
    ".m4v": "video",
    ".mov": "video",
    ".webm": "video",
    ".avi": "video",
}


def _load_config_env() -> None:
    if not CONFIG_ENV.exists():
        return
    try:
        for raw in CONFIG_ENV.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key:
                os.environ[key] = value.strip()
    except Exception:
        pass


_load_config_env()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on", "evet", "aktif"}


def _env_int(name: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        value = int(str(os.environ.get(name, default)).strip())
    except Exception:
        value = int(default)
    if min_value is not None:
        value = max(int(min_value), value)
    if max_value is not None:
        value = min(int(max_value), value)
    return value


def _db_path() -> str:
    return os.environ.get("YAZKLINIK_DB_PATH") or str(ROOT / "local_db" / "yazklinik_v68.sqlite3")


def _state_root() -> Path:
    raw = (
        os.environ.get("YAZKLINIK_STATE_ROOT")
        or os.environ.get("YAZKLINIK_TEMP_DIR")
        or str(ROOT / "runtime_state")
    )
    p = Path(raw)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _nas_root() -> str:
    return os.environ.get("YAZKLINIK_NAS_ROOT") or r"\\ASUSTOR\Voluson\Hastalar"


def sh(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=False)


def safe_attr(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _json_for_html(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def db_conn() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path(), timeout=10)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA busy_timeout=7000")
    except Exception:
        pass
    return con


def _ensure_schema(con: sqlite3.Connection | None = None) -> None:
    own = con is None
    if con is None:
        con = db_conn()
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS patient_portal_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                patient_key TEXT NOT NULL,
                patient_name TEXT,
                created_at TEXT NOT NULL,
                created_by TEXT,
                expires_at TEXT,
                revoked_at TEXT,
                last_access_at TEXT
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_patient_portal_token ON patient_portal_links(token)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_patient_portal_patient "
            "ON patient_portal_links(patient_key, created_at DESC)"
        )
        if own:
            con.commit()
    finally:
        if own:
            con.close()


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("T", " ").replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except Exception:
        return None


def _access_log(token: str, patient_key: str = "", ok: bool = True, reason: str = "") -> None:
    if not _env_bool("YAZKLINIK_PORTAL_LOG_ACCESS", True):
        return
    try:
        item = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "app": "patient_portal_public",
            "token_tail": str(token or "")[-8:],
            "patient_key": str(patient_key or ""),
            "ok": bool(ok),
            "reason": str(reason or ""),
            "path": request.path,
            "ip": request.headers.get("CF-Connecting-IP")
            or request.headers.get("X-Forwarded-For")
            or request.remote_addr
            or "",
            "ua": request.headers.get("User-Agent", "")[:180],
        }
        log_path = _state_root() / "portal_public_access.log"
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _active_link(token: str, touch: bool = False) -> dict[str, Any] | None:
    token = str(token or "").strip()
    if not TOKEN_RE.match(token):
        _access_log(token, ok=False, reason="bad-token")
        return None
    _ensure_schema()
    now_txt = datetime.now().isoformat(sep=" ", timespec="seconds")
    try:
        with db_conn() as con:
            row = con.execute(
                """
                SELECT * FROM patient_portal_links
                WHERE token = ?
                  AND COALESCE(revoked_at, '') = ''
                  AND (COALESCE(expires_at, '') = '' OR expires_at >= ?)
                LIMIT 1
                """,
                (token, now_txt),
            ).fetchone()
            if not row:
                _access_log(token, ok=False, reason="not-found-or-expired")
                return None
            item = dict(row)
            created_at = _parse_dt(item.get("created_at"))
            max_days = _env_int("YAZKLINIK_PORTAL_TOKEN_MAX_DAYS", 30, 1, 365)
            if created_at and (datetime.now() - created_at).days > max_days:
                _access_log(token, item.get("patient_key", ""), ok=False, reason="max-age")
                return None
            if touch:
                try:
                    con.execute(
                        "UPDATE patient_portal_links SET last_access_at=? WHERE token=?",
                        (now_txt, token),
                    )
                    con.commit()
                except Exception:
                    pass
            _access_log(token, item.get("patient_key", ""), ok=True, reason="ok")
            return item
    except Exception:
        _access_log(token, ok=False, reason="db-unavailable")
        return None


def _patient_row(patient_key: str) -> dict[str, Any] | None:
    patient_key = str(patient_key or "").strip()
    if not patient_key:
        return None
    try:
        with db_conn() as con:
            row = con.execute(
                """
                SELECT p.folder_key AS patient_key,
                       COALESCE(NULLIF(p.display_name, ''), p.folder_key) AS display_name,
                       COALESCE(pp.protocol_no, '') AS protocol_no,
                       COALESCE(pd.phone, '') AS phone,
                       COALESCE(pd.age, '') AS age,
                       COALESCE(pd.birth_date, '') AS birth_date
                FROM patients p
                LEFT JOIN patient_protocols pp ON pp.patient_key = p.folder_key
                LEFT JOIN patient_demographics pd ON pd.patient_key = p.folder_key
                WHERE p.folder_key = ?
                  AND COALESCE(p.archived_at, '') = ''
                LIMIT 1
                """,
                (patient_key,),
            ).fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def _latest_visit(patient_key: str) -> dict[str, Any]:
    try:
        with db_conn() as con:
            row = con.execute(
                """
                SELECT visit_date, visit_type, notes, clinical_section
                FROM visits
                WHERE patient_folder_key = ?
                  AND COALESCE(archived_at, '') = ''
                ORDER BY COALESCE(NULLIF(visit_date, ''), NULLIF(created_at, ''),
                                  NULLIF(first_seen_at, '')) DESC
                LIMIT 1
                """,
                (patient_key,),
            ).fetchone()
            return dict(row) if row else {}
    except Exception:
        return {}


def _next_appointment(patient_key: str) -> dict[str, Any]:
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with db_conn() as con:
            row = con.execute(
                """
                SELECT appointment_date, appointment_time, purpose, note
                FROM appointments
                WHERE patient_key = ?
                  AND COALESCE(status, '') != 'cancelled'
                  AND COALESCE(appointment_date, '') >= ?
                ORDER BY appointment_date ASC, appointment_time ASC
                LIMIT 1
                """,
                (patient_key, today),
            ).fetchone()
            return dict(row) if row else {}
    except Exception:
        return {}


def _last_measurement_label(patient_key: str) -> str:
    try:
        with db_conn() as con:
            row = con.execute(
                """
                SELECT ga_weeks, ga_days, efw, measured_at, created_at
                FROM usg_measurements
                WHERE patient_key = ?
                ORDER BY COALESCE(NULLIF(measured_at, ''), NULLIF(created_at, '')) DESC
                LIMIT 1
                """,
                (patient_key,),
            ).fetchone()
        if not row:
            return "-"
        weeks = row["ga_weeks"] if "ga_weeks" in row.keys() else ""
        days = row["ga_days"] if "ga_days" in row.keys() else ""
        efw = row["efw"] if "efw" in row.keys() else ""
        bits = []
        if weeks not in (None, ""):
            label = str(weeks)
            if days not in (None, ""):
                label += f"+{days}"
            bits.append(label + " hafta")
        if efw not in (None, ""):
            bits.append(f"EFW {efw}g")
        return " / ".join(bits) if bits else "-"
    except Exception:
        return "-"


def _date_display(value: Any) -> str:
    raw = str(value or "").strip()[:10]
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw)
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return raw


def _file_kind(path_or_name: Any) -> str:
    suffix = Path(str(path_or_name or "")).suffix.lower()
    return MEDIA_EXTS.get(suffix, "")


def _dedupe_key(path: Path, title: str = "") -> str:
    try:
        st = path.stat()
        return f"{path.name.lower()}:{st.st_size}:{int(st.st_mtime)}"
    except Exception:
        return f"{path.name.lower()}:{str(title or '').lower()}"


def _safe_existing_file(path_value: Any) -> Path | None:
    try:
        p = Path(str(path_value or "")).resolve()
    except Exception:
        return None
    if not p.exists() or not p.is_file():
        return None
    if _file_kind(p) not in {"image", "pdf", "video"}:
        return None
    return p


def _file_items_from_db(patient_key: str, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_pdf: set[str] = set()

    def add(path_value: Any, title: str = "", visit_key: str = "", visit_date: str = "", mtime: Any = 0) -> None:
        if len(out) >= limit:
            return
        p = _safe_existing_file(path_value)
        if not p:
            return
        kind = _file_kind(p)
        norm = str(p).lower()
        if norm in seen:
            return
        if kind == "pdf":
            pdf_key = _dedupe_key(p, title)
            if pdf_key in seen_pdf:
                return
            seen_pdf.add(pdf_key)
        seen.add(norm)
        try:
            st = p.stat()
            size = int(st.st_size or 0)
            file_mtime = float(mtime or st.st_mtime or 0)
        except Exception:
            size = 0
            file_mtime = float(mtime or 0)
        out.append(
            {
                "path": str(p),
                "title": title or p.name,
                "kind": kind,
                "visit_key": visit_key or "",
                "visit_date": visit_date or "",
                "mtime": file_mtime,
                "size": size,
            }
        )

    try:
        with db_conn() as con:
            rows = con.execute(
                """
                SELECT f.file_name, f.full_path, f.visit_key, f.mtime,
                       COALESCE(v.visit_date, '') AS visit_date
                FROM files f
                LEFT JOIN visits v
                  ON v.patient_folder_key = f.patient_folder_key
                 AND COALESCE(v.visit_key, '') = COALESCE(f.visit_key, '')
                WHERE f.patient_folder_key = ?
                  AND COALESCE(f.archived_at, '') = ''
                  AND (
                    LOWER(COALESCE(f.file_kind, '')) IN
                      ('image','jpg','jpeg','png','usg','pdf','rapor','tetkik',
                       'video','mp4','klip','cine')
                    OR LOWER(COALESCE(f.file_name, '')) LIKE '%.jpg'
                    OR LOWER(COALESCE(f.file_name, '')) LIKE '%.jpeg'
                    OR LOWER(COALESCE(f.file_name, '')) LIKE '%.png'
                    OR LOWER(COALESCE(f.file_name, '')) LIKE '%.webp'
                    OR LOWER(COALESCE(f.file_name, '')) LIKE '%.pdf'
                    OR LOWER(COALESCE(f.file_name, '')) LIKE '%.mp4'
                    OR LOWER(COALESCE(f.file_name, '')) LIKE '%.m4v'
                    OR LOWER(COALESCE(f.file_name, '')) LIKE '%.mov'
                    OR LOWER(COALESCE(f.file_name, '')) LIKE '%.webm'
                    OR LOWER(COALESCE(f.file_name, '')) LIKE '%.avi'
                  )
                ORDER BY COALESCE(f.mtime, 0) DESC, f.file_name DESC
                LIMIT ?
                """,
                (patient_key, max(20, min(limit * 3, 900))),
            ).fetchall()
        for row in rows:
            add(
                row["full_path"],
                row["file_name"],
                row["visit_key"],
                row["visit_date"],
                row["mtime"],
            )
    except Exception:
        pass
    out.sort(key=lambda item: float(item.get("mtime") or 0), reverse=True)
    return out[:limit]


def _file_items_from_nas(patient_key: str, limit: int, already: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(already) >= limit:
        return already[:limit]
    root = Path(_nas_root()) / str(patient_key or "")
    if not root.exists():
        return already[:limit]
    seen = {str(Path(x.get("path", "")).resolve()).lower() for x in already if x.get("path")}
    deadline = time.time() + 3.0
    out = list(already)
    try:
        for base, _dirs, files in os.walk(root):
            if time.time() > deadline or len(out) >= limit:
                break
            for name in files:
                if time.time() > deadline or len(out) >= limit:
                    break
                p = _safe_existing_file(Path(base) / name)
                if not p:
                    continue
                norm = str(p).lower()
                if norm in seen:
                    continue
                seen.add(norm)
                try:
                    st = p.stat()
                    mtime = float(st.st_mtime or 0)
                    size = int(st.st_size or 0)
                except Exception:
                    mtime = 0.0
                    size = 0
                out.append(
                    {
                        "path": str(p),
                        "title": p.name,
                        "kind": _file_kind(p),
                        "visit_key": "",
                        "visit_date": "",
                        "mtime": mtime,
                        "size": size,
                    }
                )
    except Exception:
        pass
    out.sort(key=lambda item: float(item.get("mtime") or 0), reverse=True)
    return out[:limit]


_FILE_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _file_items(patient_key: str, limit: int = 240) -> list[dict[str, Any]]:
    key = f"{patient_key}:{int(limit)}"
    now = time.time()
    cached = _FILE_CACHE.get(key)
    if cached and cached[0] > now:
        return cached[1]
    items = _file_items_from_db(patient_key, limit)
    items = _file_items_from_nas(patient_key, limit, items)
    _FILE_CACHE[key] = (now + 90.0, items)
    return items


def _diet_docs(patient_key: str, limit: int = 40) -> list[dict[str, Any]]:
    try:
        with db_conn() as con:
            rows = con.execute(
                """
                SELECT id, file_name, patient_label, diet_type, created_at,
                       length(pdf_blob) AS size
                FROM patient_diet_documents
                WHERE patient_key = ?
                  AND COALESCE(deleted_at, '') = ''
                ORDER BY id DESC
                LIMIT ?
                """,
                (patient_key, max(1, min(int(limit or 40), 80))),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _diet_blob(patient_key: str, doc_id: int) -> tuple[bytes, str] | None:
    try:
        with db_conn() as con:
            row = con.execute(
                """
                SELECT pdf_blob, file_name
                FROM patient_diet_documents
                WHERE id = ?
                  AND patient_key = ?
                  AND COALESCE(deleted_at, '') = ''
                LIMIT 1
                """,
                (int(doc_id), patient_key),
            ).fetchone()
        if not row:
            return None
        blob = bytes(row["pdf_blob"] or b"")
        if not blob:
            return None
        return blob, row["file_name"] or f"Diyet_{doc_id}.pdf"
    except Exception:
        return None


def _groups_for(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for index, item in enumerate(items):
        kind = str(item.get("kind") or "")
        if kind not in {"image", "video", "pdf"}:
            continue
        vdate = str(item.get("visit_date") or "")[:10]
        vkey = str(item.get("visit_key") or "").strip() or vdate or "diger"
        group = groups.get(vkey)
        if group is None:
            group = {"vkey": vkey, "date": vdate, "images": [], "videos": [], "pdfs": []}
            groups[vkey] = group
            order.append(vkey)
        if not group["date"] and vdate:
            group["date"] = vdate
        if kind == "image":
            group["images"].append((index, item))
        elif kind == "video":
            group["videos"].append((index, item))
        else:
            group["pdfs"].append((index, item))
    return sorted((groups[k] for k in order), key=lambda g: str(g.get("date") or ""), reverse=True)


def _thumb_response(path: str, max_px: int = 480):
    try:
        from PIL import Image

        src = Path(path)
        if not src.exists() or not src.is_file():
            return None
        st = src.stat()
        cache_dir = _state_root() / "portal_public_thumbs"
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.md5(
            f"{src.resolve()}|{st.st_mtime_ns}|{st.st_size}|{int(max_px)}".encode(
                "utf-8", "replace"
            )
        ).hexdigest()
        thumb_path = cache_dir / f"{key}.jpg"
        if not thumb_path.exists():
            with Image.open(src) as im:
                im = im.convert("RGB")
                im.thumbnail((int(max_px), int(max_px)))
                im.save(
                    thumb_path,
                    "JPEG",
                    quality=(85 if int(max_px) > 800 else 82),
                    optimize=True,
                )
        data = thumb_path.read_bytes()
        resp = make_response(data)
        resp.headers["Content-Type"] = "image/jpeg"
        resp.headers["Cache-Control"] = "private, max-age=86400"
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp
    except Exception:
        return None


def _send_media(path: str, kind: str = "", download: bool = False):
    p = _safe_existing_file(path)
    if not p:
        abort(404)
    kind = kind or _file_kind(p)
    mimetype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    if kind == "pdf":
        mimetype = "application/pdf"
    elif kind == "video" and not mimetype.startswith("video/"):
        mimetype = "video/mp4"
    elif kind == "image" and not mimetype.startswith("image/"):
        mimetype = "image/jpeg"
    resp = send_file(
        str(p),
        mimetype=mimetype,
        as_attachment=bool(download),
        download_name=p.name,
        conditional=True,
        max_age=0,
    )
    resp.headers["Cache-Control"] = "no-store, private, max-age=0"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


def _portal_base_url() -> str:
    return (
        os.environ.get("YAZKLINIK_PATIENT_PORTAL_BASE_URL")
        or "https://hasta.yazhakan.com.tr"
    ).strip().rstrip("/")


def _patient_html(patient: dict[str, Any], link: dict[str, Any], token: str) -> str:
    patient_key = str(patient.get("patient_key") or "")
    visit = _latest_visit(patient_key)
    appt = _next_appointment(patient_key)
    files = _file_items(patient_key, limit=240)
    groups = _groups_for(files)
    diets = _diet_docs(patient_key)

    name = sh(patient.get("display_name") or patient_key)
    protocol = sh(patient.get("protocol_no") or "-")
    age = sh(patient.get("age") or "-")
    last_visit = sh(_date_display(visit.get("visit_date")) or "-")
    ga_label = sh(_last_measurement_label(patient_key))
    expires = sh(str(link.get("expires_at") or "")[:19] or "-")
    next_line = "-"
    if appt:
        next_line = sh(
            f"{appt.get('appointment_date') or ''} {appt.get('appointment_time') or ''} "
            f"{appt.get('purpose') or ''}".strip()
        )

    diet_html = ""
    if diets:
        rows = []
        for row in diets:
            did = int(row.get("id") or 0)
            size_kb = max(1, int((int(row.get("size") or 0) + 1023) / 1024))
            rows.append(
                f'<div class="doc-row"><div><b>{sh(row.get("diet_type") or "Diyet listesi")}</b>'
                f'<span>{sh(row.get("created_at") or "")} - {size_kb} KB</span></div>'
                f'<div class="row-actions"><a href="/hasta-portal/p/{safe_attr(token)}/diyet/{did}" target="_blank" rel="noopener">Gor</a>'
                f'<a href="/hasta-portal/p/{safe_attr(token)}/diyet/{did}?download=1">Indir</a></div></div>'
            )
        diet_html = (
            '<section class="panel"><div class="label">Diyet listelerim</div>'
            f'<div class="doc-list">{"".join(rows)}</div></section>'
        )

    viewer_groups: dict[str, list[dict[str, str]]] = {}
    chips = []
    sections = []
    for idx, group in enumerate(groups):
        vid = f"v{idx}"
        label = sh(_date_display(group.get("date")) or group.get("date") or "Tarih yok")
        nimg, nvid, npdf = len(group["images"]), len(group["videos"]), len(group["pdfs"])
        chips.append(
            f'<button class="visit-chip{" active" if idx == 0 else ""}" type="button" data-visit="{vid}">'
            f'<b>{label}</b><span>{nimg} g&ouml;rsel / {nvid} video / {npdf} PDF</span></button>'
        )
        viewer_groups[vid] = []
        cards = []
        for j, (file_index, item) in enumerate(group["images"]):
            vindex = len(viewer_groups[vid])
            viewer_groups[vid].append(
                {
                    "src": f"/hasta-portal/p/{token}/file/{file_index}?view=1",
                    "thumb": f"/hasta-portal/p/{token}/file/{file_index}?thumb=1",
                    "title": str(item.get("title") or "USG"),
                }
            )
            title = sh(item.get("title") or "USG")
            if j < 9:
                cards.append(
                    f'<button class="media-card" type="button" data-visit="{vid}" data-index="{vindex}">'
                    f'<img src="/hasta-portal/p/{safe_attr(token)}/file/{file_index}?thumb=1" alt="{title}" loading="lazy" decoding="async">'
                    f'<span>{title}</span></button>'
                )
            elif j == 9:
                cards.append(
                    f'<button class="media-card media-more" type="button" data-visit="{vid}" data-index="{vindex}">'
                    f'<strong>+{nimg - 9}</strong><span>galeride gor</span></button>'
                )
        for file_index, item in group["videos"]:
            title = sh(item.get("title") or "Video")
            cards.append(
                f'<div class="media-card video-card"><video src="/hasta-portal/p/{safe_attr(token)}/file/{file_index}#t=0.1" '
                f'preload="metadata" controls playsinline></video><span>{title}</span></div>'
            )
        docs = []
        for file_index, item in group["pdfs"]:
            title = sh(item.get("title") or "PDF")
            size_kb = max(1, int((int(item.get("size") or 0) + 1023) / 1024))
            docs.append(
                f'<a class="doc-card" href="/hasta-portal/p/{safe_attr(token)}/file/{file_index}" target="_blank" rel="noopener">'
                f'<b>{title}</b><span>PDF - {size_kb} KB</span></a>'
            )
        body = ""
        if cards:
            body += f'<div class="media-grid">{"".join(cards)}</div>'
        if docs:
            body += f'<div class="doc-grid">{"".join(docs)}</div>'
        if body:
            display = "" if idx == 0 else ' style="display:none"'
            open_attr = " open" if idx == 0 else ""
            sections.append(
                f'<details class="visit-block" data-visit="{vid}"{open_attr}{display}>'
                f'<summary><b>{label}</b><span>{nimg} g&ouml;rsel / {nvid} video / {npdf} PDF</span></summary>'
                f'<div class="visit-body">{body}<a class="zip-btn" href="/hasta-portal/p/{safe_attr(token)}/zip?visit={quote(str(group["vkey"]), safe="")}">Bu geli&#351;i ZIP indir</a></div>'
                f'</details>'
            )

    if sections:
        gallery = (
            '<section class="panel"><div class="label">Tarihe g&ouml;re geli&#351; medyalar&#305;</div>'
            f'<div class="visit-chips">{"".join(chips)}</div>'
            '<p class="hint">Her tarih ayr&#305; a&ccedil;&#305;l&#305;r; sadece se&ccedil;ili geli&#351;in &ouml;nizlemeleri g&ouml;r&uuml;n&uuml;r.</p>'
            f'<div class="visit-list">{"".join(sections)}</div></section>'
        )
    else:
        gallery = (
            '<section class="panel"><div class="empty">Payla&#351;&#305;labilir g&ouml;rsel, video veya PDF bulunamad&#305;.</div></section>'
        )

    return f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <link rel="icon" href="data:,">
  <title>YazKlinik Hasta Portal</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin:0; min-height:100vh; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif; background:#eef3f8; color:#10223f; }}
    .page {{ width:min(1080px, calc(100% - 28px)); margin:0 auto; padding:28px 0; }}
    .hero {{ background:linear-gradient(140deg,#07152f,#102a56 58%,#1d4f8f); color:white; border-radius:18px; padding:24px; box-shadow:0 22px 54px rgba(7,21,47,.32); }}
    .eyebrow {{ font-size:11px; font-weight:900; letter-spacing:.1em; text-transform:uppercase; color:#dbeafe; }}
    h1 {{ margin:6px 0 4px; font-size:clamp(29px,5.8vw,46px); line-height:1.06; color:white; font-weight:950; }}
    .meta {{ color:#dbeafe; font-size:13px; font-weight:800; }}
    .chips {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:10px; margin-top:16px; }}
    .chip {{ background:white; color:#10223f; border-radius:12px; padding:11px 13px; box-shadow:0 12px 28px rgba(0,0,0,.18); }}
    .chip small {{ display:block; color:#64748b; font-size:10px; font-weight:900; text-transform:uppercase; }}
    .chip b {{ display:block; margin-top:3px; word-break:break-word; }}
    .grid {{ display:grid; grid-template-columns:1fr; gap:14px; margin-top:14px; }}
    .panel {{ background:white; border:1px solid #cbd8ea; border-radius:14px; padding:16px; box-shadow:0 10px 26px rgba(16,34,63,.08); }}
    .label {{ color:#243b66; font-size:12px; font-weight:950; text-transform:uppercase; margin-bottom:10px; }}
    .hint, .note {{ color:#516779; font-size:13px; line-height:1.5; }}
    .visit-chips {{ display:flex; gap:8px; flex-wrap:wrap; }}
    .visit-chip {{ display:inline-flex; flex-direction:column; gap:3px; border:1px solid #b8c8e3; border-radius:12px; background:white; color:#10223f; padding:9px 12px; cursor:pointer; text-align:left; }}
    .visit-chip.active {{ background:#102a56; color:white; border-color:#102a56; }}
    .visit-chip span {{ font-size:11px; opacity:.82; }}
    .visit-block {{ border:1px solid #cbd8ea; border-radius:14px; background:white; margin-top:12px; overflow:hidden; }}
    .visit-block summary {{ list-style:none; cursor:pointer; padding:13px 16px; display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; background:#eef5ff; }}
    .visit-block summary::-webkit-details-marker {{ display:none; }}
    .visit-body {{ padding:12px 14px 16px; }}
    .media-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:12px; }}
    .media-card {{ border:1px solid #cbd8ea; border-radius:12px; padding:7px; background:#f8fbff; cursor:pointer; text-align:left; color:#10223f; transition:transform .12s, box-shadow .12s; }}
    .media-card:hover {{ transform:translateY(-2px); box-shadow:0 12px 26px rgba(16,34,63,.16); }}
    .media-card img, .video-card video {{ width:100%; aspect-ratio:1.1; object-fit:cover; border-radius:9px; display:block; background:#e6edf8; }}
    .media-card span {{ display:block; margin-top:6px; font-size:12px; font-weight:800; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .media-more {{ display:flex; min-height:150px; flex-direction:column; align-items:center; justify-content:center; background:linear-gradient(135deg,#102a56,#1d4ed8); color:white; border:none; }}
    .media-more strong {{ font-size:32px; line-height:1; }}
    .doc-grid, .doc-list {{ display:grid; gap:10px; margin-top:10px; }}
    .doc-card, .doc-row {{ border:1px solid #cbd8ea; border-radius:12px; padding:12px 14px; background:#f8fbff; color:#10223f; text-decoration:none; }}
    .doc-card span, .doc-row span {{ display:block; margin-top:4px; color:#5f7483; font-size:12px; font-weight:700; }}
    .doc-row {{ display:flex; justify-content:space-between; gap:10px; align-items:center; flex-wrap:wrap; }}
    .row-actions {{ display:flex; gap:8px; flex-wrap:wrap; }}
    .row-actions a, .zip-btn {{ display:inline-flex; align-items:center; justify-content:center; border-radius:10px; padding:8px 12px; background:#1d4ed8; color:white; font-weight:900; text-decoration:none; border:0; margin-top:10px; }}
    .empty {{ color:#516779; font-weight:800; }}
    .viewer {{ position:fixed; inset:0; background:rgba(4,17,29,.88); display:none; align-items:center; justify-content:center; z-index:20; padding:56px 16px 42px; }}
    .viewer.show {{ display:flex; }}
    .viewer img {{ max-width:96vw; max-height:90vh; border-radius:14px; box-shadow:0 22px 70px rgba(0,0,0,.45); background:white; }}
    .viewer button {{ position:absolute; border:0; border-radius:12px; background:white; color:#10223f; font-weight:900; padding:10px 14px; cursor:pointer; }}
    .viewer .close {{ right:18px; top:18px; }}
    .viewer .prev, .viewer .next {{ top:50%; transform:translateY(-50%); font-size:34px; line-height:1; }}
    .viewer .prev {{ left:18px; }}
    .viewer .next {{ right:18px; }}
    .viewer-meta {{ position:absolute; left:18px; right:18px; bottom:14px; color:#e6fffb; text-align:center; font-size:13px; }}
    @media (max-width:620px) {{
      .page {{ width:calc(100% - 18px); padding:18px 0; }}
      .chips {{ grid-template-columns:1fr 1fr; }}
      .media-grid {{ grid-template-columns:repeat(auto-fill,minmax(140px,1fr)); gap:9px; }}
      .media-card img, .video-card video {{ aspect-ratio:1; }}
    }}
  </style>
</head>
<body>
  <main class="page" aria-label="Hasta portal">
    <section class="hero">
      <div class="eyebrow">YazKlinik Hasta Portal</div>
      <h1>{name}</h1>
      <div class="meta">Protokol: {protocol} &middot; Link gecerlilik: {expires}</div>
      <div class="chips">
        <div class="chip"><small>Yas</small><b>{age}</b></div>
        <div class="chip"><small>Son gelis</small><b>{last_visit}</b></div>
        <div class="chip"><small>Gebelik / olcum</small><b>{ga_label}</b></div>
        <div class="chip"><small>Sonraki randevu</small><b>{next_line}</b></div>
        <div class="chip"><small>Dosya</small><b>{len(groups)} tarihli gelis</b></div>
      </div>
    </section>
    <section class="grid">
      {diet_html}
      {gallery}
    </section>
    <p class="note">Bu sayfa sadece kliniginizin sizin icin paylastigi dosyalari gosterir. Acil durumda 112'yi arayiniz.</p>
  </main>
  <div class="viewer" id="portalViewer" aria-hidden="true">
    <button class="close" type="button" data-action="close">Kapat</button>
    <button class="prev" type="button" data-action="prev">&#8249;</button>
    <img id="portalViewerImg" alt="Hasta g&ouml;rseli">
    <button class="next" type="button" data-action="next">&#8250;</button>
    <div class="viewer-meta" id="portalViewerMeta"></div>
  </div>
  <script>
    (function() {{
      var viewerGroups = {_json_for_html(viewer_groups)};
      var viewer = document.getElementById('portalViewer');
      var img = document.getElementById('portalViewerImg');
      var meta = document.getElementById('portalViewerMeta');
      var idx = 0;
      var activeVisit = Object.keys(viewerGroups)[0] || '';
      function items() {{ return viewerGroups[activeVisit] || []; }}
      function show(visitId, i) {{
        activeVisit = visitId || activeVisit;
        var list = items();
        if (!list.length) return;
        idx = (i + list.length) % list.length;
        var it = list[idx];
        img.src = it.thumb || it.src;
        if (it.thumb && it.src && it.thumb !== it.src) {{
          var want = idx; var hi = new Image();
          hi.onload = function() {{ if (idx === want) img.src = it.src; }};
          hi.src = it.src;
        }}
        meta.textContent = (idx + 1) + ' / ' + list.length + ' - ' + (it.title || '');
        viewer.classList.add('show');
        viewer.setAttribute('aria-hidden', 'false');
        [idx + 1, idx - 1].forEach(function(k) {{
          var j = ((k % list.length) + list.length) % list.length;
          if (list[j]) {{ var preload = new Image(); preload.src = list[j].src; }}
        }});
      }}
      document.querySelectorAll('.media-card[data-index]').forEach(function(btn) {{
        btn.addEventListener('click', function() {{
          show(btn.getAttribute('data-visit') || activeVisit, parseInt(btn.dataset.index || '0', 10));
        }});
      }});
      document.querySelectorAll('.visit-chip').forEach(function(chip) {{
        chip.addEventListener('click', function() {{
          document.querySelectorAll('.visit-chip').forEach(function(x) {{ x.classList.remove('active'); }});
          chip.classList.add('active');
          activeVisit = chip.getAttribute('data-visit') || activeVisit;
          document.querySelectorAll('.visit-block').forEach(function(block) {{
            if (block.getAttribute('data-visit') === activeVisit) {{
              block.style.display = ''; block.setAttribute('open', '');
            }} else {{
              block.style.display = 'none'; block.removeAttribute('open');
            }}
          }});
        }});
      }});
      document.addEventListener('click', function(ev) {{
        var action = ev.target && ev.target.getAttribute ? ev.target.getAttribute('data-action') : '';
        if (action === 'close') {{ viewer.classList.remove('show'); viewer.setAttribute('aria-hidden','true'); }}
        if (action === 'prev') show(activeVisit, idx - 1);
        if (action === 'next') show(activeVisit, idx + 1);
      }});
      document.addEventListener('keydown', function(ev) {{
        if (!viewer || !viewer.classList.contains('show')) return;
        if (ev.key === 'Escape') {{ viewer.classList.remove('show'); viewer.setAttribute('aria-hidden','true'); }}
        if (ev.key === 'ArrowLeft') show(activeVisit, idx - 1);
        if (ev.key === 'ArrowRight') show(activeVisit, idx + 1);
      }});
      if (viewer) {{
        viewer.addEventListener('wheel', function(ev) {{
          if (!viewer.classList.contains('show')) return;
          ev.preventDefault(); show(activeVisit, idx + (ev.deltaY > 0 ? 1 : -1));
        }}, {{passive:false}});
      }}
    }})();
  </script>
</body>
</html>"""


def _landing_html() -> str:
    return """<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>YazKlinik Hasta Portal</title>
  <style>
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; display:grid; place-items:center; padding:22px;
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
      background:linear-gradient(135deg,#e8eef7,#f6f8fc); color:#10223f; }
    .card { width:min(760px,100%); background:white; border:1px solid #cbd8ea;
      border-radius:18px; padding:24px; box-shadow:0 16px 44px rgba(16,34,63,.12); }
    .brand { font-weight:950; font-size:30px; line-height:1.06; color:#102a56; }
    .sub { margin-top:8px; color:#4b6273; font-size:16px; line-height:1.5; }
    .line { margin-top:16px; padding:12px; border:1px dashed #9db6da; border-radius:12px; background:#f8fbff; font-weight:700; }
  </style>
</head>
<body>
  <main class="card">
    <div class="brand">Op. Dr. Hakan YAZ<br>YazKlinik Hasta Portal</div>
    <p class="sub">Bu adres hastalar icin ayrilmis guvenli portal programidir.</p>
    <div class="line">Kisisel linkiniz yoksa klinikten yeni karekod isteyiniz.</div>
  </main>
</body>
</html>"""


def _error_html(message: str, status: int = 403):
    resp = make_response(
        f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hasta Portal</title><body style="font-family:Segoe UI,Arial,sans-serif;background:#eef3f8;color:#10223f;padding:32px">
<main style="max-width:680px;margin:40px auto;background:white;border:1px solid #cbd8ea;border-radius:16px;padding:24px">
<h1 style="margin-top:0">Hasta Portal</h1><p>{sh(message)}</p></main></body>""",
        int(status),
    )
    return resp


app = Flask("yazklinik_patient_portal_public")
app.config["MAX_CONTENT_LENGTH"] = 900 * 1024 * 1024


def _allowed_host() -> bool:
    raw_host = str(request.host or "").split(":", 1)[0].strip().lower()
    allowed = {
        "hasta.yazhakan.com.tr",
        "localhost",
        "127.0.0.1",
        "::1",
    }
    env_hosts = os.environ.get("YAZKLINIK_PATIENT_PORTAL_PUBLIC_HOSTS") or ""
    for item in env_hosts.split(","):
        item = item.strip().lower()
        if item:
            allowed.add(item)
    if raw_host in allowed:
        return True
    if raw_host.startswith("192.168.") or raw_host.startswith("10.") or raw_host.startswith("172."):
        return True
    return False


@app.before_request
def _guard_host_and_paths():
    if not _allowed_host():
        return _error_html("Bu portal sadece hasta.yazhakan.com.tr uzerinden acilir.", 421)
    path = request.path or ""
    blocked_prefixes = (
        "/giris",
        "/login",
        "/hastalar",
        "/hasta-portal-admin",
        "/sistem-ayarlari",
        "/api/agents",
    )
    if any(path == one or path.startswith(one + "/") for one in blocked_prefixes):
        abort(404)
    return None


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if (request.path or "").startswith("/hasta-portal/p/"):
        resp.headers["Cache-Control"] = "no-store, private, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


@app.route("/healthz")
@app.route("/api/terminal/ping-fast")
def healthz():
    return {"ok": True, "service": "patient_portal_public", "db": _db_path()}


@app.route("/")
@app.route("/hasta-portal")
def portal_landing():
    token = str(request.args.get("token") or "").strip()
    if token and TOKEN_RE.match(token):
        return redirect(f"/hasta-portal/p/{token}", code=302)
    return _landing_html()


@app.route("/hasta-portal/p/<token>")
def portal_public_page(token: str):
    link = _active_link(token, touch=True)
    if not link:
        return _error_html(
            "Hasta portal baglantisi gecersiz veya suresi dolmus. Klinikle yeni karekod isteyiniz.",
            403,
        )
    patient = _patient_row(link.get("patient_key") or "")
    if not patient:
        return _error_html("Hasta kaydi bulunamadi veya arsivlenmis.", 404)
    return _patient_html(patient, link, token)


@app.route("/hasta-portal/p/<token>/file/<int:index>")
def portal_public_file(token: str, index: int):
    link = _active_link(token)
    if not link:
        abort(404)
    patient_key = str(link.get("patient_key") or "")
    files = _file_items(patient_key, limit=240)
    if index < 0 or index >= len(files):
        abort(404)
    item = files[index]
    if item.get("kind") == "image":
        if request.args.get("thumb"):
            resp = _thumb_response(item["path"], 480)
            if resp is not None:
                return resp
        if request.args.get("view"):
            resp = _thumb_response(item["path"], 1400)
            if resp is not None:
                return resp
    return _send_media(item["path"], item.get("kind") or "", bool(request.args.get("download")))


@app.route("/hasta-portal/p/<token>/zip")
def portal_public_zip(token: str):
    link = _active_link(token)
    if not link:
        abort(404)
    patient_key = str(link.get("patient_key") or "")
    want_visit = str(request.args.get("visit") or "").strip()
    files = _file_items(patient_key, limit=240)
    if not want_visit:
        groups = _groups_for(files)
        if groups:
            want_visit = str(groups[0].get("vkey") or "").strip()
    buf = io.BytesIO()
    added = 0
    total = 0
    cap_bytes = 700 * 1024 * 1024
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for item in files:
            if item.get("kind") not in {"image", "video", "pdf"}:
                continue
            vdate = str(item.get("visit_date") or "")[:10]
            eff = str(item.get("visit_key") or "").strip() or vdate or "diger"
            if want_visit and eff != want_visit:
                continue
            p = _safe_existing_file(item.get("path"))
            if not p:
                continue
            try:
                size = int(p.stat().st_size or 0)
            except Exception:
                size = 0
            if added > 0 and total + size > cap_bytes:
                break
            folder = re.sub(r"[^0-9A-Za-z._-]", "_", vdate or "gelis")
            base = p.name
            arc = f"{folder}/{base}"
            n = 1
            while arc in used:
                stem, ext = os.path.splitext(base)
                arc = f"{folder}/{stem}_{n}{ext}"
                n += 1
            try:
                zf.write(str(p), arcname=arc)
            except Exception:
                continue
            used.add(arc)
            added += 1
            total += size
    if not added:
        abort(404)
    data = buf.getvalue()
    filename = re.sub(r"[^0-9A-Za-z._-]", "_", f"hasta_gelis_{want_visit or 'son'}") + ".zip"
    resp = make_response(data)
    resp.headers["Content-Type"] = "application/zip"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.headers["Content-Length"] = str(len(data))
    return resp


@app.route("/hasta-portal/p/<token>/diyet/<int:doc_id>")
def portal_public_diet(token: str, doc_id: int):
    link = _active_link(token)
    if not link:
        abort(404)
    blob = _diet_blob(str(link.get("patient_key") or ""), int(doc_id))
    if not blob:
        abort(404)
    data, filename = blob
    resp = send_file(
        io.BytesIO(data),
        mimetype="application/pdf",
        download_name=filename,
        as_attachment=bool(request.args.get("download")),
        max_age=0,
    )
    resp.headers["Cache-Control"] = "no-store, private, max-age=0"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


def main() -> None:
    host = os.environ.get("YAZKLINIK_PATIENT_PORTAL_HOST") or "127.0.0.1"
    port = _env_int("YAZKLINIK_PATIENT_PORTAL_PORT", 5053, 1, 65535)
    threads = _env_int("YAZKLINIK_PATIENT_PORTAL_THREADS", 8, 2, 32)
    _ensure_schema()
    try:
        from waitress import serve

        print(
            f"YazKlinik patient portal listening on http://{host}:{port} "
            f"base={_portal_base_url()}",
            flush=True,
        )
        serve(app, host=host, port=port, threads=threads)
    except Exception:
        app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
