"""MeiliSearch Ajani - anlik tam metin arama (ChromaDB yanina, alternatif).

Niye: ChromaDB semantic ("anlam"), MeiliSearch keyword ("isim/protokol/tarih
tam eslesme + typo tolere"). Hasta adi "Kilic Sevall" yazsan da bulur.

Sema:
    yk_patients  - folder_key, display_name, phone, archived_at
    yk_visits    - id, patient_folder_key, visit_date, visit_type, notes
    yk_rx        - prescriptions (varsa)

Sync:
    sync_all_from_sqlite(dry_run=False)  - tum tablolari yeniden indeksle
    sync_incremental()                   - son N dakikadaki kayitlari

Env:
    MEILI_MASTER_KEY (akillilik/.env'den okur)
"""
from __future__ import annotations

import json
import os
import re as _re_sanitize_global
import sqlite3
import time
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-meilisearch"

DEFAULT_SQLITE_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                       or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")


def _load_env_file(path: str = r"D:\YazKlinik_Final_D300\akillilik\.env") -> Dict[str, str]:
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except Exception:
        pass
    return out


def _url() -> str:
    return os.environ.get("YAZKLINIK_MEILI_URL") or "http://localhost:17700"


def _key() -> str:
    return (os.environ.get("MEILI_MASTER_KEY")
            or _load_env_file().get("MEILI_MASTER_KEY", "")
            or "CHANGE_yk_meili_master_key_min_16")


_client = None


def get_client():
    global _client
    if _client is not None:
        return _client
    try:
        import meilisearch
        _client = meilisearch.Client(_url(), _key(), timeout=5)
        _client.health()
    except Exception:
        _client = None
    return _client


def health_check() -> Dict[str, Any]:
    out = {"ok": False, "agent_version": AGENT_VERSION, "url": _url()}
    c = get_client()
    if not c:
        out["error"] = "MeiliSearch erisilmez"
        return out
    try:
        h = c.health()
        out["ok"] = True
        out["status"] = getattr(h, "status", "available") if h else "unknown"
        try:
            v = c.get_version()
            out["version"] = v.get("pkgVersion") if isinstance(v, dict) else getattr(v, "pkg_version", "?")
        except Exception:
            out["version"] = "?"
        try:
            stats = c.get_all_stats()
            ix = stats.get("indexes", {}) if isinstance(stats, dict) else getattr(stats, "indexes", {})
            out["indexes"] = {
                name: (info.get("numberOfDocuments") if isinstance(info, dict)
                       else getattr(info, "number_of_documents", 0))
                for name, info in (ix.items() if hasattr(ix, "items") else [])
            }
        except Exception:
            out["indexes"] = {}
    except Exception as e:
        out["error"] = str(e)
    return out


def ensure_indexes() -> Dict[str, Any]:
    """3 index olustur: yk_patients, yk_visits, yk_rx. Idempotent."""
    out = {"ok": False, "indexes": [], "errors": []}
    c = get_client()
    if not c:
        out["error"] = "client yok"
        return out
    schema = [
        {"uid": "yk_patients",
         "pk": "folder_key",
         "searchable": ["display_name", "phone", "folder_key"],
         "filterable": ["archived_at"]},
        {"uid": "yk_visits",
         "pk": "id",
         "searchable": ["notes", "examination", "patient_folder_key", "visit_type"],
         "filterable": ["visit_type", "source", "patient_folder_key"]},
        {"uid": "yk_rx",
         "pk": "id",
         "searchable": ["medications", "diagnosis", "notes", "patient_name"],
         "filterable": ["created_by", "patient_key"]},
    ]
    for s in schema:
        try:
            try:
                c.get_index(s["uid"])
            except Exception:
                c.create_index(s["uid"], {"primaryKey": s["pk"]})
                time.sleep(0.4)  # async task settle
            idx = c.index(s["uid"])
            idx.update_searchable_attributes(s["searchable"])
            idx.update_filterable_attributes(s["filterable"])
            out["indexes"].append(s["uid"])
        except Exception as e:
            out["errors"].append(f"{s['uid']}: {e}")
    out["ok"] = bool(out["indexes"])
    return out


def sync_table(table: str, sqlite_path: Optional[str] = None,
                batch_size: int = 500, dry_run: bool = False) -> Dict[str, Any]:
    """Tek tabloyu MeiliSearch'e gonder."""
    out = {"ok": False, "table": table, "dry_run": dry_run,
           "rows_in_sqlite": 0, "rows_pushed": 0, "errors": []}
    src = sqlite_path or DEFAULT_SQLITE_PATH
    c = get_client()
    if not c:
        out["error"] = "client yok"
        return out

    sq = sqlite3.connect(src)
    sq.row_factory = sqlite3.Row
    try:
        def _cols(t):
            return [r[1] for r in sq.execute(f"PRAGMA table_info({t})").fetchall()]

        if table == "yk_patients":
            pcols = _cols("patients")
            select_cols = [c for c in ("folder_key", "display_name",
                                         "phone", "tc_no", "archived_at",
                                         "first_seen_at", "updated_at")
                           if c in pcols]
            select = ", ".join(select_cols)
            rows = sq.execute(
                f"SELECT {select} FROM patients WHERE folder_key IS NOT NULL"
            ).fetchall()
        elif table == "yk_visits":
            vcols = _cols("visits")
            has_visit_key = "visit_key" in vcols
            select_cols = ["rowid"]
            if has_visit_key:
                select_cols.append("visit_key")
            for c in ("patient_folder_key", "visit_date", "visit_type",
                       "notes", "examination", "source", "control_note",
                       "clinical_section", "file_count"):
                if c in vcols:
                    select_cols.append(c)
            select = ", ".join(select_cols)
            raw_rows = sq.execute(f"SELECT {select} FROM visits").fetchall()
            # ID daima rowid bazli (visit_key bazi satirlarda duplicate olabilir)
            rows = []
            for r in raw_rows:
                d = {k: r[k] for k in r.keys()}
                rid = d.pop("rowid", None)
                if has_visit_key:
                    d.pop("visit_key", None)
                d["id"] = f"v{rid}" if rid is not None else None
                rows.append(d)
        elif table == "yk_rx":
            # prescriptions tablosu var mi
            tbl_exists = sq.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='prescriptions'"
            ).fetchone()
            if not tbl_exists:
                out["ok"] = True
                out["error"] = "prescriptions tablosu yok"
                return out
            rows = sq.execute(
                "SELECT id, patient_key, patient_name, medications, "
                "diagnosis, notes, created_by FROM prescriptions").fetchall()
        else:
            out["error"] = f"unknown table {table}"
            return out

        out["rows_in_sqlite"] = len(rows)
        if dry_run:
            out["ok"] = True
            return out
        # Defansif dict + truncate uzun text + ensure id
        docs = []
        for r in rows:
            if isinstance(r, dict):
                d = dict(r)
            else:
                d = {k: r[k] for k in r.keys()}
            raw_id = d.get("id")
            if raw_id is None or raw_id == "":
                continue
            d["id"] = _re_sanitize_global.sub(r"[^A-Za-z0-9_-]", "_", str(raw_id))[:511]
            if not d["id"]:
                continue
            for f in ("notes", "examination", "medications", "diagnosis"):
                v = d.get(f)
                if isinstance(v, str) and len(v) > 10000:
                    d[f] = v[:10000] + "...[trunc]"
            docs.append(d)
        idx = c.index(table)
        for i in range(0, len(docs), batch_size):
            batch = docs[i:i + batch_size]
            try:
                idx.add_documents(batch)
                out["rows_pushed"] += len(batch)
            except Exception as e:
                out["errors"].append(f"batch {i}: {e}")
        out["ok"] = (out["rows_pushed"] > 0)
    except Exception as e:
        out["errors"].append(str(e))
    finally:
        sq.close()
    return out


def sync_all_from_sqlite(sqlite_path: Optional[str] = None,
                          dry_run: bool = False) -> Dict[str, Any]:
    """3 tabloyu MeiliSearch'e tam sync."""
    out = {"ok": False, "sync_results": [], "started_at": time.time()}
    ensure_indexes()
    for table in ("yk_patients", "yk_visits", "yk_rx"):
        r = sync_table(table, sqlite_path=sqlite_path, dry_run=dry_run)
        out["sync_results"].append(r)
    out["ok"] = all(r.get("ok") for r in out["sync_results"])
    out["duration_sec"] = round(time.time() - out["started_at"], 2)
    return out


def search(query: str, index_uid: str = "yk_patients",
            limit: int = 20, filters: Optional[str] = None) -> Dict[str, Any]:
    """Tam metin arama. Tipik kullanim:
       search('kilic sevall', 'yk_patients')  # typo tolerant
       search('preeklampsi', 'yk_visits', filters='visit_type = konsult')
    """
    out = {"ok": False, "query": query, "index": index_uid, "hits": [], "total": 0}
    c = get_client()
    if not c:
        out["error"] = "client yok"
        return out
    try:
        idx = c.index(index_uid)
        params = {"limit": int(limit), "attributesToHighlight": ["*"]}
        if filters:
            params["filter"] = filters
        res = idx.search(str(query), params)
        if isinstance(res, dict):
            out["hits"] = res.get("hits", [])
            out["total"] = res.get("estimatedTotalHits", 0)
            out["processing_time_ms"] = res.get("processingTimeMs", 0)
        else:
            out["hits"] = getattr(res, "hits", [])
            out["total"] = getattr(res, "estimated_total_hits", 0)
        out["ok"] = True
    except Exception as e:
        out["error"] = str(e)
    return out


def delete_index(uid: str) -> bool:
    """Test/reset icin."""
    c = get_client()
    if not c:
        return False
    try:
        c.delete_index(uid)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    print("HEALTH:", json.dumps(health_check(), ensure_ascii=False, indent=2))
    print("\nENSURE INDEXES:", json.dumps(ensure_indexes(), ensure_ascii=False, indent=2))
    print("\nDRY-RUN SYNC ALL:", json.dumps(sync_all_from_sqlite(dry_run=True), ensure_ascii=False, indent=2))
