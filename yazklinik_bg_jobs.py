# -*- coding: utf-8 -*-
"""
YazKlinik Background Job Manager
=================================
Paylasilan arka plan is yoneticisi - sayfa terkedilebilir, geri donulebilir,
sonuc hazir bekler.

Kullanim:
    from yazklinik_bg_jobs import bg_start_job, bg_get_job, bg_get_last_job, bg_list_jobs

    # Baslat
    jid = bg_start_job("nas_sync", run_nas_sync_fn, "arg1", user_key="doktor", kwarg=1)

    # Sorgula
    job = bg_get_job(jid)
    if job["status"] == "done":
        print(job["result"])

    # Kullanicinin son jobu (sayfaya geri donen kullanici icin)
    last = bg_get_last_job("doktor", "nas_sync")

    # Kullanicinin tum jobs gecmisi
    jobs = bg_list_jobs("doktor", job_type="nas_sync")  # job_type opsiyonel

Tasarim:
    - In-memory dict (process-local, restart'ta silinir)
    - 1 saatten eski tamamlanmis joblar otomatik temizlenir
    - Thread-safe (threading.Lock)
    - daemon=True (sunucu kapanirken thread'ler durur)

Bu modul Instagram scan icin yazildi, sonra PubMed/RAG/NAS'a da uygulandi.
"""
from __future__ import annotations
import threading
import time
import secrets
from typing import Callable, Optional, Any, List, Dict


_BACKGROUND_JOBS: Dict[str, Any] = {}  # job_id -> dict | last-pointer
_BG_LOCK = threading.Lock()
_JOB_TTL_SECONDS = 3600  # 1 saat


def _cleanup_locked():
    """Eski tamamlanmis joblar temizle (lock icinde cagrilmali)."""
    cutoff = time.time() - _JOB_TTL_SECONDS
    to_del = [k for k, v in _BACKGROUND_JOBS.items()
              if isinstance(v, dict) and v.get("completed_at") and v["completed_at"] < cutoff]
    for k in to_del:
        del _BACKGROUND_JOBS[k]


def bg_start_job(job_type: str, fn: Callable, *args,
                 user_key: str = "", **kwargs) -> str:
    """Arka plan jobu baslat. Donus: job_id.

    fn(*args, **kwargs) ayri thread'de calisir. Sonuc job dict'ine yazilir.

    Args:
        job_type: 'ig_scan', 'pubmed_scan', 'rag_reindex', 'nas_sync' vb.
        fn: cagrilacak fonksiyon
        *args, **kwargs: fn'e gecirilecek argumanlar
        user_key: bu kullanicinin "son jobu" olarak takip etmek icin

    Returns:
        job_id - sonra bg_get_job(job_id) ile sorgula
    """
    job_id = f"{job_type}_{int(time.time())}_{secrets.token_hex(4)}"
    job: Dict[str, Any] = {
        "id": job_id, "type": job_type,
        "status": "pending", "progress": 0,
        "result": None, "error": None,
        "started_at": time.time(), "completed_at": None,
        "user_key": user_key,
    }
    with _BG_LOCK:
        _BACKGROUND_JOBS[job_id] = job
        if user_key:
            _BACKGROUND_JOBS[f"_last_{user_key}_{job_type}"] = job_id
        _cleanup_locked()

    def _worker():
        job["status"] = "running"
        try:
            result = fn(*args, **kwargs)
            with _BG_LOCK:
                job["result"] = result
                job["status"] = "done"
                job["progress"] = 100
                job["completed_at"] = time.time()
        except Exception as e:
            with _BG_LOCK:
                job["error"] = f"{type(e).__name__}: {e}"
                job["status"] = "failed"
                job["completed_at"] = time.time()

    threading.Thread(target=_worker, daemon=True).start()
    return job_id


def bg_get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Job'u id ile getir. None = bulunamadi/sildi."""
    with _BG_LOCK:
        v = _BACKGROUND_JOBS.get(job_id)
        return v if isinstance(v, dict) else None


def bg_get_last_job(user_key: str, job_type: str) -> Optional[Dict[str, Any]]:
    """Kullanicinin verilen tipte son jobunu getir.

    Sayfa terkedildikten sonra geri donen kullanici icin:
    geri donunce 'son jobum vardi, sonuc hazir mi?' kontrolu yap.
    """
    with _BG_LOCK:
        last_id = _BACKGROUND_JOBS.get(f"_last_{user_key}_{job_type}")
        if last_id:
            v = _BACKGROUND_JOBS.get(last_id)
            return v if isinstance(v, dict) else None
    return None


def bg_list_jobs(user_key: str, job_type: Optional[str] = None,
                 limit: int = 20) -> List[Dict[str, Any]]:
    """Kullanicinin job gecmisini getir (en yeniden eskiye)."""
    out: List[Dict[str, Any]] = []
    with _BG_LOCK:
        for jid, j in list(_BACKGROUND_JOBS.items()):
            if not isinstance(j, dict):
                continue
            if j.get("user_key") != user_key:
                continue
            if job_type and j.get("type") != job_type:
                continue
            out.append({
                "job_id": jid,
                "type": j.get("type"),
                "status": j.get("status"),
                "started_at": j.get("started_at"),
                "completed_at": j.get("completed_at"),
                "progress": j.get("progress"),
                "error": j.get("error"),
            })
    out.sort(key=lambda x: x.get("started_at") or 0, reverse=True)
    return out[:limit]


def bg_set_progress(job_id: str, pct: int, note: str = "") -> None:
    """Job'un yuzdelik ilerlemesini guncelle (worker icinden cagrilir)."""
    with _BG_LOCK:
        v = _BACKGROUND_JOBS.get(job_id)
        if isinstance(v, dict):
            v["progress"] = max(0, min(100, int(pct)))
            if note:
                v["progress_note"] = note


def bg_cancel_old(older_than_seconds: int = 3600) -> int:
    """Belirli yastan eski tamamlanmis joblari sil. Donus: silinen sayi."""
    cutoff = time.time() - older_than_seconds
    deleted = 0
    with _BG_LOCK:
        keys = [k for k, v in _BACKGROUND_JOBS.items()
                if isinstance(v, dict) and v.get("completed_at") and v["completed_at"] < cutoff]
        for k in keys:
            del _BACKGROUND_JOBS[k]
            deleted += 1
    return deleted


# Backwards compatibility: agents_routes.py'nin eski private isimleriyle de
# calisabilsin (gecis donemi icin)
_bg_start_job = bg_start_job
_bg_get_job = bg_get_job
_bg_get_last_job = bg_get_last_job
