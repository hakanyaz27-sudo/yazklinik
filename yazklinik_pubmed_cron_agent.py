"""PubMed Otomatik Tarama Cron Ajani.

Doktor onceden tanimladigi sorgu listesini (PubMed keywords) gunluk tarar:
    - Yeni cikan makaleleri tespit
    - Top 3'unu Turkce ozetler
    - RAG'a auto-index
    - Doktor inbox'una mail/WhatsApp "Bugunun yeni makaleleri" gonderir
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-pubmed-cron"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")


# Hekimin daimi taranan sorgulari
DEFAULT_QUERIES = [
    "preeclampsia 2024 management",
    "polycystic ovary syndrome treatment update",
    "fetal growth restriction biometry",
    "cervical cancer screening HPV",
    "endometriosis treatment laparoscopy",
    "gestational diabetes screening",
    "postpartum depression PHQ-9",
    "uterine fibroid embolization",
]


@dataclass
class PubMedHit:
    pmid: str
    title: str
    abstract: str = ""
    pub_year: str = ""
    journal: str = ""
    indexed_in_rag: bool = False
    translated_summary: str = ""


@dataclass
class CronScanResult:
    ran_at: str
    queries: List[str]
    new_hits: List[PubMedHit] = field(default_factory=list)
    total_indexed: int = 0
    digest_markdown: str = ""
    sent_to_doctor: bool = False
    agent_version: str = AGENT_VERSION


def _ensure_table(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS pubmed_seen_pmids (
            pmid TEXT PRIMARY KEY,
            query TEXT,
            seen_at TEXT,
            indexed INTEGER DEFAULT 0
        )""")
        con.commit()
    finally:
        con.close()


def _is_new(pmid: str, db_path: str) -> bool:
    con = sqlite3.connect(db_path)
    try:
        row = con.execute("SELECT 1 FROM pubmed_seen_pmids WHERE pmid = ?",
                          (pmid,)).fetchone()
        return not row
    finally:
        con.close()


def _mark_seen(pmid: str, query: str, db_path: str, indexed: bool = False):
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "INSERT OR REPLACE INTO pubmed_seen_pmids (pmid, query, seen_at, indexed) "
            "VALUES (?, ?, datetime('now'), ?)", (pmid, query, 1 if indexed else 0))
        con.commit()
    finally:
        con.close()


def scan(queries: Optional[List[str]] = None,
          max_per_query: int = 3,
          db_path: Optional[str] = None,
          send_to_doctor: bool = True) -> CronScanResult:
    """PubMed tara, yeni olanlari ozetle + RAG'a indeksle."""
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    queries = queries or DEFAULT_QUERIES
    r = CronScanResult(ran_at=datetime.now().isoformat(timespec="seconds"),
                        queries=queries)

    try:
        from yazklinik_ceviri_agent import search_pubmed, translate_pubmed_article
    except Exception as e:
        r.digest_markdown = f"# Hata\n\nceviri_agent import edilemedi: {e}"
        return r

    md_lines = [f"# PubMed Tarama Ozeti ({r.ran_at[:10]})\n"]
    for q in queries:
        try:
            sr = search_pubmed(q, max_results=max_per_query) or {}
            hits = sr.get("hits", []) if isinstance(sr, dict) else []
            md_lines.append(f"## Sorgu: `{q}` ({len(hits)} bulundu)\n")
            for h in hits[:max_per_query]:
                pmid = str(h.get("pmid") or "")
                if not pmid or not _is_new(pmid, db_path):
                    continue
                hit = PubMedHit(
                    pmid=pmid, title=h.get("title", "")[:200],
                    journal=h.get("journal", ""), pub_year=h.get("year", ""))
                try:
                    tr = translate_pubmed_article(pmid, auto_index_rag=True)
                    if tr and getattr(tr, "summary_tr", None):
                        hit.translated_summary = tr.summary_tr[:300]
                    hit.indexed_in_rag = True
                    r.total_indexed += 1
                    _mark_seen(pmid, q, db_path, indexed=True)
                except Exception as e:
                    _mark_seen(pmid, q, db_path, indexed=False)
                r.new_hits.append(hit)
                md_lines.append(f"- **{hit.title}** ({hit.journal} {hit.pub_year})")
                md_lines.append(f"  PMID: {pmid}")
                if hit.translated_summary:
                    md_lines.append(f"  > {hit.translated_summary}")
                md_lines.append("")
        except Exception as e:
            md_lines.append(f"- Sorgu hatası: {e}\n")

    r.digest_markdown = "\n".join(md_lines)

    if send_to_doctor and r.new_hits:
        try:
            from yazklinik_whatsapp_local_helper import send_whatsapp_message
            doctor_phone = os.environ.get("DOCTOR_WHATSAPP", "")
            if doctor_phone:
                msg = f"PubMed yeni: {len(r.new_hits)} makale, RAG'a {r.total_indexed} eklendi.\nPanel: /alex-rag-merkezi"
                send_whatsapp_message(doctor_phone, msg)
                r.sent_to_doctor = True
        except Exception:
            pass

    return r


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "default_queries": len(DEFAULT_QUERIES)}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
