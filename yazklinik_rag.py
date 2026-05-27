"""Alex RAG (Retrieval-Augmented Generation) altyapÄ±.

Hasta dosyalarÄ±, USG raporlarÄ±, araÅŸtÄ±rma Ã¶zetleri, doktor notlarÄ± semantic
search ile indekslenir. Alex her sorguda en alakalÄ± 3-5 belgeyi otomatik
prompt'a inject eder.

Embedding model: paraphrase-multilingual-mpnet-base-v2 (TÃ¼rkÃ§e destekli, ~420MB)
Vector DB: ChromaDB embedded (SQLite backend, server gerek yok)

Ä°lk Ã§alÄ±ÅŸtÄ±rmada model otomatik indirilir (~1-2 dakika), sonra cache'den Ã§alÄ±ÅŸÄ±r.
"""
from __future__ import annotations

import os
import sys
import sqlite3
import threading
import time
import json
from pathlib import Path
from typing import Optional


# === FFmpeg DLL path enjeksiyon (torchcodec icin) ===
# torch>=2.4 + transformers torchcodec yukluyor, o da FFmpeg DLL ister.
# Ortam degiskeni veya bilinen lokasyon.
def _yk_inject_ffmpeg_path():
    candidates = [
        r"D:\YazKlinik_Final_D500\models\ffmpeg\extracted",
        r"D:\YazKlinik_Final_D500\tools\ffmpeg",
    ]
    for root in candidates:
        if not os.path.isdir(root):
            continue
        # Recursive: */bin/ altinda ffmpeg.exe var mi
        for sub in os.listdir(root):
            bindir = os.path.join(root, sub, "bin")
            if os.path.isdir(bindir) and any(
                    f.lower().endswith(".dll") for f in os.listdir(bindir)):
                os.environ["PATH"] = bindir + os.pathsep + os.environ.get("PATH", "")
                try:
                    os.add_dll_directory(bindir)
                except (AttributeError, OSError):
                    pass
                return bindir
    return None


_yk_inject_ffmpeg_path()


# ============================================================================
# KONFIG
# ============================================================================

BASE = Path(__file__).parent if "__file__" in globals() else Path.cwd()
RAG_DIR = BASE / "rag_data"
CHROMA_DIR = RAG_DIR / "chroma"
EMBED_CACHE_DIR = RAG_DIR / "embed_cache"
COLLECTION_NAME = "alex_knowledge"

# D700 2026-05-17: BGE-M3 (BAAI) - multilingual SOTA, Turkce mukemmel
# Eski default: paraphrase-multilingual-mpnet-base-v2 (2 yillik)
# Yenisi:      BAAI/bge-m3 - daha buyuk context (8192), daha dogru skor
# ENV ile ezerlenebilir: ALEX_EMBED_MODEL=eski-model-adi
EMBED_MODEL = os.environ.get(
    "ALEX_EMBED_MODEL",
    "BAAI/bge-m3")

# Reranker: ilk-asama retrieve + ikinci-asama yeniden sirala = cok daha dogru
# BGE-Reranker-v2-m3 multilingual, Turkce destekli
RERANKER_MODEL = os.environ.get(
    "ALEX_RERANKER_MODEL",
    "BAAI/bge-reranker-v2-m3")

# Reranker'i kullan? (paket yuklu degilse otomatik kapanir)
USE_RERANKER = os.environ.get("ALEX_USE_RERANKER", "1") not in ("0", "false", "no")

# Default: relevance threshold (cosine distance < bu ise ilgili)
# BGE-M3 skorlari MPNet'ten farkli; ENV ile override edilebilir
RELEVANCE_THRESHOLD = float(os.environ.get("ALEX_RAG_THRESHOLD", "0.7"))
TOP_K = int(os.environ.get("ALEX_RAG_TOP_K", "5"))

# Reranker icin: ilk asamada bu kadar cek, sonra reranker top_k'ya kucult
RERANK_FETCH_K = int(os.environ.get("ALEX_RAG_RERANK_FETCH_K", "15"))

_MODEL = None
_RERANKER = None
_CLIENT = None
_COLLECTION = None
_LOCK = threading.Lock()


# ============================================================================
# LAZY INIT
# ============================================================================

def _get_model():
    """sentence-transformers modelini lazy yÃ¼kle."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    with _LOCK:
        if _MODEL is not None:
            return _MODEL
        from sentence_transformers import SentenceTransformer
        EMBED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(EMBED_CACHE_DIR))
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(EMBED_CACHE_DIR))
        t0 = time.time()
        try:
            print(f"[RAG] Model yukleniyor: {EMBED_MODEL}", flush=True)
        except Exception:
            pass
        # CUDA varsa kullan (RTX 5090'da ~5x hÄ±zlÄ±)
        device = "cuda"
        try:
            import torch
            if not torch.cuda.is_available():
                device = "cpu"
        except Exception:
            device = "cpu"
        _MODEL = SentenceTransformer(EMBED_MODEL, device=device,
                                     cache_folder=str(EMBED_CACHE_DIR))
        try:
            print(f"[RAG] Model OK ({time.time()-t0:.1f}s, {device})", flush=True)
        except Exception:
            pass
    return _MODEL


def _get_reranker():
    """BGE-Reranker-v2-m3 lazy yukle. Paket yoksa None doner."""
    global _RERANKER
    if not USE_RERANKER:
        return None
    if _RERANKER is not None:
        return _RERANKER if _RERANKER is not False else None
    with _LOCK:
        if _RERANKER is not None:
            return _RERANKER if _RERANKER is not False else None
        try:
            from rerankers import Reranker  # type: ignore
            t0 = time.time()
            try:
                print(f"[RAG] Reranker yukleniyor: {RERANKER_MODEL}", flush=True)
            except Exception:
                pass
            # rerankers paketi otomatik device sececek (cuda varsa)
            _RERANKER = Reranker(RERANKER_MODEL, model_type="cross-encoder")
            try:
                print(f"[RAG] Reranker OK ({time.time()-t0:.1f}s)", flush=True)
            except Exception:
                pass
        except Exception as exc:
            try:
                print(f"[RAG] Reranker yuklenemedi: {exc} - reranker'siz devam",
                      flush=True)
            except Exception:
                pass
            _RERANKER = False
            return None
    return _RERANKER if _RERANKER is not False else None


def rerank_results(query, results, top_k=None):
    """Verilen sonuc listesini reranker ile yeniden sirala.

    results: search() ciktisi. Her oge {"text":..., "score":..., ...}
    Returns: ayni format, score = reranker raw_score (0..1 normalize).
    Paket/model yuklenemezse: orijinal sirayi koru, dokunma.
    """
    rr = _get_reranker()
    if rr is None or not results:
        return results
    try:
        docs = [r.get("text", "") for r in results]
        # rerankers Reranker.rank() Results dondurur, .top_k(N) ile kucult
        ranked = rr.rank(query=str(query), docs=docs)
        # Score'a gore yeniden sirala
        order = []
        for r in ranked.results:
            idx = getattr(r, "doc_id", None)
            if idx is None:
                continue
            sc = getattr(r, "score", None)
            order.append((int(idx), float(sc) if sc is not None else 0.0))
        if not order:
            return results
        # Index'e gore esle, score'u koy, ardindan sirala
        out = []
        for idx, sc in order:
            if 0 <= idx < len(results):
                item = dict(results[idx])
                item["score"] = round(sc, 4)
                item["reranked"] = True
                out.append(item)
        if top_k:
            out = out[:int(top_k)]
        return out
    except Exception as exc:
        try:
            print(f"[RAG] rerank HATA, orijinal koruna: {exc}", flush=True)
        except Exception:
            pass
        return results


def _get_collection():
    """ChromaDB collection - lazy."""
    global _CLIENT, _COLLECTION
    if _COLLECTION is not None:
        return _COLLECTION
    with _LOCK:
        if _COLLECTION is not None:
            return _COLLECTION
        import chromadb
        from chromadb.config import Settings
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _CLIENT = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False, allow_reset=True))
        _COLLECTION = _CLIENT.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Alex bilgi tabanÄ±: hasta, USG, araÅŸtÄ±rma"})
    return _COLLECTION


# ============================================================================
# EMBEDDING + INDEX
# ============================================================================

def embed_text(text):
    """Text -> embedding vector (numpy array)."""
    if not text or not str(text).strip():
        return None
    m = _get_model()
    return m.encode(str(text).strip(), convert_to_numpy=True,
                    normalize_embeddings=True).tolist()


def embed_batch(texts):
    """Birden Ã§ok text -> embedding listesi (batch, hÄ±zlÄ±)."""
    if not texts:
        return []
    m = _get_model()
    arr = m.encode([str(t).strip() for t in texts],
                   convert_to_numpy=True, normalize_embeddings=True,
                   batch_size=32, show_progress_bar=False)
    return [v.tolist() for v in arr]


def index_document(doc_id, text, metadata=None):
    """Tek belge index'le (varsa overwrite)."""
    if not text or not str(text).strip():
        return False
    col = _get_collection()
    emb = embed_text(text)
    meta = dict(metadata or {})
    meta.setdefault("indexed_ts", int(time.time() * 1000))
    # ChromaDB metadata sadece str/int/float/bool kabul eder
    clean_meta = {k: (str(v) if not isinstance(v, (str, int, float, bool))
                      else v) for k, v in meta.items()}
    col.upsert(ids=[str(doc_id)], embeddings=[emb],
               documents=[str(text)[:4000]], metadatas=[clean_meta])
    return True


def index_documents_batch(docs):
    """[(doc_id, text, metadata), ...] -> tek seferde index."""
    if not docs:
        return 0
    col = _get_collection()
    ids = [str(d[0]) for d in docs]
    texts = [str(d[1])[:4000] for d in docs]
    metas = []
    for d in docs:
        meta = dict(d[2] or {})
        meta.setdefault("indexed_ts", int(time.time() * 1000))
        clean = {k: (str(v) if not isinstance(v, (str, int, float, bool))
                     else v) for k, v in meta.items()}
        metas.append(clean)
    embs = embed_batch(texts)
    # BoÅŸ embedding olanlarÄ± at
    keep_idx = [i for i, e in enumerate(embs) if e is not None]
    if not keep_idx:
        return 0
    col.upsert(
        ids=[ids[i] for i in keep_idx],
        embeddings=[embs[i] for i in keep_idx],
        documents=[texts[i] for i in keep_idx],
        metadatas=[metas[i] for i in keep_idx])
    return len(keep_idx)


def delete_document(doc_id):
    try:
        col = _get_collection()
        col.delete(ids=[str(doc_id)])
        return True
    except Exception:
        return False


def search(query, top_k=TOP_K, threshold=RELEVANCE_THRESHOLD,
           kind_filter=None, use_reranker=None, fetch_k=None):
    """Sorguya en yakÄ±n belgeleri bul (2-asamali: retrieve + opsiyonel rerank).

    Args:
      query        : Sorgu metni
      top_k        : Son cikti boyutu
      threshold    : Retrieve asamasi cosine distance esigi (vector benzerligi)
      kind_filter  : metadata.kind filtre (orn 'usg', 'research')
      use_reranker : None=USE_RERANKER env'e bak, True/False=zorla
      fetch_k      : Reranker icin ilk asamada N belge cek (top_k * 3 onerilir).
                     Reranker yoksa yok sayilir.

    Returns: [{id, text, metadata, distance, score, reranked?}, ...]
      score: reranker varsa reranker skor (0..1, yuksek = daha iyi)
             reranker yoksa 1-distance (1=tam eslesme)
    """
    if not query or not str(query).strip():
        return []
    col = _get_collection()
    emb = embed_text(query)
    if not emb:
        return []
    where = {"kind": kind_filter} if kind_filter else None

    # Reranker var/yok karari
    want_rerank = use_reranker if use_reranker is not None else USE_RERANKER
    n_retrieve = int(fetch_k or RERANK_FETCH_K) if want_rerank else int(top_k)
    n_retrieve = max(n_retrieve, int(top_k))

    try:
        res = col.query(query_embeddings=[emb], n_results=n_retrieve,
                        where=where)
    except Exception as exc:
        try: print(f"[RAG] search HATA: {exc}", flush=True)
        except Exception: pass
        return []
    out = []
    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    for i in range(len(ids)):
        d = float(dists[i]) if i < len(dists) and dists[i] is not None else 1.0
        # Retrieve asamasi threshold: gevsek tut, reranker daha sert yapar
        if d > threshold:
            continue
        out.append({
            "id": ids[i],
            "text": docs[i] if i < len(docs) else "",
            "metadata": metas[i] if i < len(metas) else {},
            "distance": d,
            "score": round(1.0 - d, 3),
        })

    # Ikinci asama: reranker (mevcutsa)
    if want_rerank and out:
        rr = _get_reranker()
        if rr is not None:
            try:
                out = rerank_results(query, out, top_k=int(top_k))
            except Exception as exc:
                try: print(f"[RAG] rerank skip: {exc}", flush=True)
                except Exception: pass
                out = out[:int(top_k)]
        else:
            out = out[:int(top_k)]
    else:
        out = out[:int(top_k)]

    return out


# ============================================================================
# AUTO-INDEX: alex_researches + voluson_reports + alex_facts
# ============================================================================

def auto_index_all(db_path=None, force=False):
    """Mevcut DB tablolarindaki tum belgeleri index'le.

    force=False ise sadece son 24 saatte index'lenmemis kayitlari ekler.
    Returns: dict {researches, voluson, facts, patients, total}
    """
    if db_path is None:
        db_path = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")
    con = __import__("yazklinik_db_adapter").agent_connection(sqlite_path=db_path)  # PG-primary aware
    con.execute("PRAGMA journal_mode=WAL")
    stats = {"researches": 0, "voluson": 0, "facts": 0, "learnings": 0,
             "patients": 0, "total": 0}
    try:
        # 1) alex_researches
        try:
            rows = con.execute(
                "SELECT id, source, query, summary FROM alex_researches "
                "WHERE summary IS NOT NULL AND length(summary) > 30").fetchall()
            docs = []
            for rid, src, q, summ in rows:
                text = f"[{src.upper() if src else 'web'} arastirma] {q}: {summ}"
                docs.append((f"research_{rid}", text,
                            {"kind": "research", "source": src or "",
                             "query": q or "", "row_id": rid}))
            n = index_documents_batch(docs)
            stats["researches"] = n
        except Exception as exc:
            print(f"[RAG] research index HATA: {exc}")
        # 2) voluson_reports
        try:
            rows = con.execute(
                "SELECT id, patient_name, patient_key, exam_date, ga_aua, "
                "efw_g, efw_percentile, bpd_mm, ac_mm, fl_mm, fetal_hr, "
                "umb_pi, clinical_flags FROM voluson_reports "
                "WHERE patient_key IS NOT NULL").fetchall()
            docs = []
            for r in rows:
                rid, pname, pkey, exd, ga, efw, efp, bpd, ac, fl, hr, pi, flags = r
                try:
                    fl_list = json.loads(flags or "[]") if flags else []
                except Exception:
                    fl_list = []
                parts = [f"Hasta {pname or pkey} - USG {exd or ''}"]
                if ga: parts.append(f"Gebelik haftasi: {ga}")
                if efw:
                    parts.append(f"EFW: {efw}g" +
                                 (f" ({efp:.1f} persantil)" if efp else ""))
                if bpd: parts.append(f"BPD: {bpd:.1f}mm")
                if ac: parts.append(f"AC: {ac:.1f}mm")
                if fl: parts.append(f"FL: {fl:.1f}mm")
                if hr: parts.append(f"Fetal kalp atimi: {hr} bpm")
                if pi: parts.append(f"Umbilikal arter PI: {pi:.2f}")
                if fl_list:
                    parts.append("Klinik flags: " + "; ".join(fl_list))
                text = ". ".join(parts) + "."
                docs.append((f"usg_{rid}", text,
                            {"kind": "usg", "patient_key": pkey or "",
                             "patient_name": pname or "",
                             "exam_date": exd or "", "ga": ga or "",
                             "row_id": rid}))
            n = index_documents_batch(docs)
            stats["voluson"] = n
        except Exception as exc:
            print(f"[RAG] voluson index HATA: {exc}")
        # 3) alex_facts (kalici bilgi)
        try:
            rows = con.execute(
                "SELECT id, category, fact, user_key FROM alex_facts").fetchall()
            docs = []
            for rid, cat, fact, uk in rows:
                if not fact or len(fact) < 5:
                    continue
                text = f"[{cat or 'genel'}] {fact}"
                docs.append((f"fact_{rid}", text,
                            {"kind": "fact", "category": cat or "",
                             "user_key": uk or "", "row_id": rid}))
            n = index_documents_batch(docs)
            stats["facts"] = n
        except Exception as exc:
            print(f"[RAG] facts index HATA: {exc}")
        # 4) alex_learned_summaries (Yaz LLM uzun hafiza)
        try:
            rows = con.execute(
                "SELECT id, source, summary, user_key "
                "FROM alex_learned_summaries "
                "WHERE summary IS NOT NULL AND length(summary) > 8").fetchall()
            docs = []
            for rid, src, summary, uk in rows:
                if not summary:
                    continue
                text = f"[Yaz LLM hafiza / {src or 'dialog'}] {summary}"
                docs.append((f"learning_{rid}", text,
                            {"kind": "learning", "source": src or "",
                             "user_key": uk or "", "row_id": rid}))
            n = index_documents_batch(docs)
            stats["learnings"] = n
        except Exception as exc:
            print(f"[RAG] learned index HATA: {exc}")
        # 5) patients (folder index)
        try:
            rows = con.execute(
                "SELECT folder_key, display_name FROM patients "
                "WHERE archived_at IS NULL").fetchall()
            docs = []
            for fk, dn in rows:
                if not (fk and dn):
                    continue
                text = f"Hasta: {dn} (klasor: {fk})"
                docs.append((f"patient_{fk}", text,
                            {"kind": "patient", "folder_key": fk,
                             "display_name": dn}))
            n = index_documents_batch(docs)
            stats["patients"] = n
        except Exception as exc:
            print(f"[RAG] patient index HATA: {exc}")
    finally:
        con.close()
    stats["total"] = sum(v for k, v in stats.items() if k != "total")
    return stats


# ============================================================================
# PROMPT INJECTION
# ============================================================================

def format_results_for_prompt(results, max_chars_each=400):
    """RAG sonuÃ§larÄ±nÄ± prompt'a uygun string formatÄ±na Ã§evir."""
    if not results:
        return ""
    lines = ["[ALAKALI BILGI - kullanici sorusuna en yakin 3-5 belge]"]
    for r in results:
        meta = r.get("metadata", {})
        kind = meta.get("kind", "?")
        score = r.get("score", 0)
        text = r.get("text", "")
        if len(text) > max_chars_each:
            text = text[:max_chars_each].rsplit(" ", 1)[0] + "..."
        tag = {"research": "ARASTIRMA", "usg": "USG", "fact": "BILGI",
               "learning": "HAFIZA", "patient": "HASTA"}.get(
                   kind, kind.upper())
        lines.append(f"- [{tag} Â· skor {score}] {text}")
    return "\n".join(lines)


def retrieve_for_query(query, top_k=5, threshold=0.7):
    """Voice-turn'da cagrilacak. Sorgu ile alakali belgeleri prompt-ready string olarak don."""
    results = search(query, top_k=top_k, threshold=threshold)
    return format_results_for_prompt(results)


# ============================================================================
# MANUEL UPLOAD: PDF/metin -> chunk + index
# ============================================================================

def _chunk_text(text, max_chars=800, overlap=80):
    """Uzun metni RAG icin chunklara ayir (overlap ile)."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks = []
    i = 0
    while i < len(text):
        end = i + max_chars
        # Cumle sonuna kadar uzat (en yakin nokta/yenisatir)
        if end < len(text):
            for off in range(min(100, len(text)-end)):
                if text[end+off] in ".!?\n":
                    end += off + 1
                    break
        chunks.append(text[i:end].strip())
        i = end - overlap
        if i < 0:
            i = 0
        if end >= len(text):
            break
    return [c for c in chunks if c]


def index_text_document(title, text, kind="manual", source="upload",
                       meta_extra=None):
    """Bir metni chunk'lara ayir + her chunk'i index'le.

    Returns: (doc_count, total_chunks).
    """
    chunks = _chunk_text(text, max_chars=800, overlap=80)
    if not chunks:
        return 0, 0
    safe_title = "".join(c if c.isalnum() else "_" for c in (title or "doc"))[:40]
    docs = []
    for i, chunk in enumerate(chunks):
        doc_id = f"upload_{safe_title}_{int(time.time())}_{i}"
        meta = {"kind": kind, "source": source, "title": title or "manual",
                "chunk": i, "total_chunks": len(chunks)}
        if meta_extra:
            meta.update(meta_extra)
        docs.append((doc_id, chunk, meta))
    n = index_documents_batch(docs)
    return 1, n


def index_pdf_file(pdf_path, title=None):
    """PDF dosyasini parse et + RAG'a yukle."""
    try:
        import fitz
    except ImportError:
        return False, "PyMuPDF (fitz) yuklu degil"
    if not os.path.exists(pdf_path):
        return False, f"Dosya yok: {pdf_path}"
    try:
        doc = fitz.open(pdf_path)
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text("text"))
        doc.close()
        text = "\n\n".join(text_parts).strip()
        if not text:
            return False, "PDF metni cikarilamadi (gorsel-only olabilir)"
        title = title or os.path.basename(pdf_path).rsplit(".", 1)[0]
        _, n = index_text_document(
            title, text, kind="pdf", source=pdf_path,
            meta_extra={"original_filename": os.path.basename(pdf_path)})
        return True, f"{n} chunk index'lendi: {title}"
    except Exception as exc:
        return False, str(exc)


# ============================================================================
# CLI test
# ============================================================================

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nKomutlar:")
        print("  python yazklinik_rag.py index           # Tum DB'yi index'le")
        print("  python yazklinik_rag.py search '<soru>' # Search test")
        print("  python yazklinik_rag.py stats           # Collection durum")
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "index":
        print("Auto-index basliyor...")
        t0 = time.time()
        s = auto_index_all()
        print(f"Sure: {time.time()-t0:.1f}s")
        for k, v in s.items():
            print(f"  {k}: {v}")
    elif cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: search '<query>'"); sys.exit(1)
        q = sys.argv[2]
        results = search(q, top_k=5)
        print(f"Sorgu: {q}\nSonuc: {len(results)}\n")
        for r in results:
            print(f"  [skor {r['score']}] {r['metadata'].get('kind','?')}: "
                  f"{r['text'][:120]}")
    elif cmd == "stats":
        col = _get_collection()
        n = col.count()
        print(f"Collection: {COLLECTION_NAME}")
        print(f"Belge sayisi: {n}")
        print(f"Chroma path: {CHROMA_DIR}")

