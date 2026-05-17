"""Celery + Redis Background Worker Iskeleti.

Heavy jobs (PubMed RAG, USG batch process, lab fetch) icin asenkron isleyici.

Production icin:
    pip install celery[redis]
    celery -A yazklinik_celery_worker worker --loglevel=info --pool=solo  # windows
    celery -A yazklinik_celery_worker beat                                  # schedule
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-celery"

REDIS_URL = os.environ.get("REDIS_URL", "redis://:redispass@localhost:6379/2")
CELERY_BROKER = os.environ.get("CELERY_BROKER", REDIS_URL)
CELERY_RESULT = os.environ.get("CELERY_RESULT", REDIS_URL)


try:
    from celery import Celery
    _has_celery = True
except ImportError:
    _has_celery = False
    Celery = None  # type: ignore


if _has_celery:
    app = Celery("yazklinik", broker=CELERY_BROKER, backend=CELERY_RESULT)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Europe/Istanbul",
        enable_utc=False,
        task_track_started=True,
        task_time_limit=1800,         # 30 dk hard
        task_soft_time_limit=1500,    # 25 dk soft
        worker_max_tasks_per_child=50,
    )

    @app.task(name="yazklinik.pubmed_translate", bind=True, max_retries=2)
    def pubmed_translate_task(self, pmid: str, auto_index: bool = True):
        try:
            from yazklinik_ceviri_agent import translate_pubmed_article
            return translate_pubmed_article(pmid, auto_index_rag=auto_index)
        except Exception as e:
            raise self.retry(exc=e, countdown=60)

    @app.task(name="yazklinik.usg_analyze", bind=True, max_retries=1)
    def usg_analyze_task(self, image_path: str, patient_key: str = "", lmp: str = ""):
        from yazklinik_orchestrator_agent import usg_full_pipeline
        return str(usg_full_pipeline(image_path, patient_key, lmp))

    @app.task(name="yazklinik.daily_summary")
    def daily_summary_task():
        from yazklinik_gunluk_ozet_agent import build_summary
        return build_summary()

    @app.task(name="yazklinik.nightly_backup")
    def nightly_backup_task():
        import subprocess
        try:
            r = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File",
                 r"D:\YazKlinik_Final_D300\akillilik\scripts\restic_daily_backup.ps1"],
                capture_output=True, text=True, timeout=3600)
            return {"returncode": r.returncode, "stdout": r.stdout[-500:],
                    "stderr": r.stderr[-500:]}
        except Exception as e:
            return {"error": str(e)}

    app.conf.beat_schedule = {
        "daily-summary-19h": {
            "task": "yazklinik.daily_summary",
            "schedule": 3600.0 * 24,  # 24h
            "options": {"queue": "default"},
        },
        "nightly-backup-2am": {
            "task": "yazklinik.nightly_backup",
            "schedule": 3600.0 * 24,
            "options": {"queue": "long"},
        },
    }

else:
    app = None

    def pubmed_translate_task(*a, **k):
        return {"error": "celery yok - pip install celery[redis]"}

    def usg_analyze_task(*a, **k):
        return {"error": "celery yok - pip install celery[redis]"}

    def daily_summary_task(*a, **k):
        return {"error": "celery yok - pip install celery[redis]"}

    def nightly_backup_task(*a, **k):
        return {"error": "celery yok - pip install celery[redis]"}


def health_check() -> Dict[str, Any]:
    return {"ok": _has_celery, "agent_version": AGENT_VERSION,
            "celery_available": _has_celery, "broker": CELERY_BROKER,
            "note": "Worker baslat: celery -A yazklinik_celery_worker worker --pool=solo"
                     if _has_celery else "pip install celery[redis]"}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
