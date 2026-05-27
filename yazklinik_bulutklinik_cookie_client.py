"""BulutKlinik cookie tabanli HTTP client.

API Client ID/Secret yerine kullanicinin browser cookies'i ile baglanir.
bulutklinik_session.json dosyasini okur, requests Session'a uygular,
internal endpoint'lere baglanir.

Cookies 24-72 saat gecerli. Bittiginde:
  python bulutklinik_cookie_cdp.py     # yeniden cek
"""
from __future__ import annotations
import os, json, time, re, html
from typing import Optional, Dict, Any, List

try:
    import requests
except ImportError:
    requests = None

BASE = "https://app.bulutklinik.com"
SESSION_FILE = r"D:\YazKlinik_Final_D500\bulutklinik_session.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/147.0 Safari/537.36")


class BulutklinikCookieClient:
    """Cookie tabanli BulutKlinik HTTP wrapper."""

    def __init__(self, session_file: str = SESSION_FILE):
        if requests is None:
            raise RuntimeError("requests yuklu degil")
        self.session_file = session_file
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
        })
        self.last_check = 0
        self.is_authenticated = False
        self._load_cookies()

    def _load_cookies(self) -> bool:
        if not os.path.exists(self.session_file):
            return False
        with open(self.session_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = data.get("raw_cookies") or []
        if not cookies:
            ss = data.get("storage_state") or {}
            cookies = ss.get("cookies") or []
        for c in cookies:
            try:
                self.session.cookies.set(
                    c["name"], c["value"],
                    domain=c.get("domain") or BASE,
                    path=c.get("path", "/"))
            except Exception:
                pass
        return True

    def session_info(self) -> Dict[str, Any]:
        if not os.path.exists(self.session_file):
            return {"exists": False}
        with open(self.session_file, "r", encoding="utf-8") as f:
            d = json.load(f)
        age_h = (time.time() - d.get("saved_at", 0)) / 3600
        return {
            "exists": True,
            "cookies_count": d.get("cookies_count", 0),
            "saved_at": d.get("saved_at", 0),
            "age_hours": round(age_h, 1),
            "expired": age_h > 72,
            "source": d.get("source", ""),
        }

    def check_auth(self, force: bool = False) -> bool:
        """Cookies hala gecerli mi? Cache 5 dk."""
        if not force and self.is_authenticated and (time.time() - self.last_check) < 300:
            return True
        try:
            r = self.session.get(BASE + "/App/My/favorites.gg",
                                 timeout=15, allow_redirects=True)
            self.last_check = time.time()
            self.is_authenticated = "/Login" not in r.url
            return self.is_authenticated
        except Exception:
            return False

    def get(self, path: str, **kw) -> "requests.Response":
        url = path if path.startswith("http") else BASE + path
        return self.session.get(url, timeout=kw.pop("timeout", 20), **kw)

    def post(self, path: str, **kw) -> "requests.Response":
        url = path if path.startswith("http") else BASE + path
        return self.session.post(url, timeout=kw.pop("timeout", 30), **kw)

    def fetch_html(self, path: str) -> str:
        """HTML cek, login'e yonlendirilirse exception."""
        r = self.get(path)
        if "/Login" in r.url:
            self.is_authenticated = False
            raise RuntimeError("Cookie expire - yeniden cookie cek")
        return r.text

    # === Yuksek seviye helper'lar ===

    def get_dashboard(self) -> Dict[str, Any]:
        """Ana favorites.gg sayfasi - ozet bilgi."""
        html_text = self.fetch_html("/App/My/favorites.gg")
        return {
            "ok": True,
            "size": len(html_text),
            "title": self._extract_title(html_text),
            "user_name": self._extract_user_name(html_text),
            "html_excerpt": html_text[:500],
        }

    def search_patients(self, query: str = "", limit: int = 20) -> List[Dict]:
        """Hasta listesi/arama. Path heuristic - asagidakileri sırasıyla deneyecek."""
        paths_to_try = [
            f"/App/Hasta/Liste?q={query}",
            f"/App/Hasta/Search?q={query}",
            "/App/Hasta",
            "/App/My/hastalar.gg",
        ]
        for path in paths_to_try:
            try:
                r = self.get(path, timeout=15)
                if r.status_code == 200 and "/Login" not in r.url:
                    return self._parse_patient_list(r.text, limit=limit)
            except Exception:
                continue
        return []

    def get_appointments_today(self) -> List[Dict]:
        paths_to_try = [
            "/App/Randevu/Liste",
            "/App/Randevu",
            "/App/My/randevular.gg",
        ]
        for path in paths_to_try:
            try:
                r = self.get(path, timeout=15)
                if r.status_code == 200 and "/Login" not in r.url:
                    return self._parse_appointment_list(r.text)
            except Exception:
                continue
        return []

    # === Calendar API (cookie-based) ===

    def get_my_events(self, range_: str = "today") -> Dict[str, Any]:
        """Randevuları çek. range: today | tomorrow | last_week | next_week.

        Donus formati: {"success": True, "data": {"events": [...], "total": N}}
        """
        if range_ not in ("today", "tomorrow", "last_week", "next_week"):
            range_ = "today"
        try:
            r = self.get("/App/My/get_my_events",
                         params={"range": range_}, timeout=15)
            d = r.json()
            data = d.get("data") or {}
            return {
                "ok": bool(d.get("success")),
                "message": d.get("message", ""),
                "events": data.get("events") or [],
                "total": data.get("total") or 0,
                "range": data.get("range") or range_,
            }
        except Exception as e:
            return {"ok": False, "message": str(e), "events": [], "total": 0,
                    "range": range_}

    def calendar_search_patient(self, query: str,
                                limit: int = 25) -> List[Dict]:
        """Calendar autocomplete - hasta ara.

        Donus: [{"id": "1", "TEXT": "AD SOYAD - TEL - DT", "name": "...", "phone": "..."}, ...]
        """
        try:
            r = self.post("/Cln/Calendar/patient_search",
                          data={"search": query, "q": query, "term": query},
                          timeout=15)
            d = r.json()
            results = d.get("results") or []
            out = []
            for it in results[:limit]:
                txt = (it.get("TEXT") or it.get("text") or "").strip()
                # Format: "AD SOYAD - TC_KIMLIK - TELEFON"
                parts = [p.strip() for p in txt.split(" - ")]
                name = parts[0] if parts else txt
                tc = parts[1] if len(parts) > 1 else ""
                phone = parts[2] if len(parts) > 2 else ""
                out.append({
                    "id": it.get("id"),
                    "name": name,
                    "tc": tc,
                    "phone": phone,
                    "text": txt,
                    "raw": it,
                })
            return out
        except Exception:
            return []

    def get_doctor_work_schedule(self) -> List[Dict]:
        """Doktor genel çalışma takvimi."""
        try:
            r = self.get("/Cln/Calendar/getDoctorGeneralWorkSchedule",
                         timeout=15)
            d = r.json()
            return d if isinstance(d, list) else []
        except Exception:
            return []

    # === Database Toplu Export (CSV / XLSX) ===

    EXPORT_CATEGORIES = {
        0: ("hastalar",    "Hastalar",          "csv"),
        1: ("hizmetler",   "Hizmetler",         "csv"),
        2: ("protokoller", "Protokoller",       "csv"),
        3: ("tahsilatlar", "Tahsilatlar",       "csv"),
        4: ("randevular",  "Randevular",        "csv"),
        5: ("medikal",     "Medikal Bilgiler",  "csv"),
        6: ("obstetri",    "Obstetri",          "xlsx"),
        7: ("jinekoloji",  "Jinekoloji",        "xlsx"),
    }

    def export_category(self, category_id: int) -> Dict[str, Any]:
        """Tek bir kategori ZIP/CSV/XLSX indir.

        Donus: {ok, content (bytes), filename, content_type, size,
                category_id, category_name}
        """
        if category_id not in self.EXPORT_CATEGORIES:
            return {"ok": False, "error": f"Gecersiz kategori: {category_id}"}
        slug, name, ext = self.EXPORT_CATEGORIES[category_id]
        try:
            r = self.get(f"/Sec/Security/export_data/{category_id}",
                         timeout=120, allow_redirects=True)
            if r.status_code != 200 or len(r.content) < 100:
                return {"ok": False, "error": f"HTTP {r.status_code}, "
                        f"{len(r.content)} byte"}
            ct = r.headers.get("Content-Type", "application/octet-stream")
            cd = r.headers.get("Content-Disposition", "")
            fnm_m = re.search(
                r'filename[*]?=(?:UTF-8\'\')?["\']?([^;"\']+)', cd)
            filename = (fnm_m.group(1).strip() if fnm_m
                        else f"{slug}.{ext}")
            return {
                "ok": True,
                "content": r.content,
                "filename": filename,
                "content_type": ct,
                "size": len(r.content),
                "category_id": category_id,
                "category_name": name,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def export_all(self, out_dir: str) -> Dict[str, Any]:
        """8 kategoriyi de indir, out_dir'a kaydet. ZIP yapmadan."""
        import os
        os.makedirs(out_dir, exist_ok=True)
        results = []
        total = 0
        for cid in sorted(self.EXPORT_CATEGORIES.keys()):
            r = self.export_category(cid)
            if r.get("ok"):
                fnm = r["filename"]
                # Filename'i guvenli yap (windows path safe)
                safe = re.sub(r'[^\w\-_.]', '_', fnm)
                if not safe or len(safe) > 80:
                    slug = self.EXPORT_CATEGORIES[cid][0]
                    ext = self.EXPORT_CATEGORIES[cid][2]
                    safe = f"{slug}.{ext}"
                path = os.path.join(out_dir, safe)
                with open(path, "wb") as f:
                    f.write(r["content"])
                results.append({"category_id": cid,
                                "name": r["category_name"],
                                "filename": safe, "size": r["size"],
                                "path": path, "ok": True})
                total += r["size"]
            else:
                results.append({"category_id": cid,
                                "name": self.EXPORT_CATEGORIES[cid][1],
                                "ok": False,
                                "error": r.get("error", "?")})
        return {"ok": True, "out_dir": out_dir, "files": results,
                "total_bytes": total, "count": len(results)}

    # === HTML parse helpers (heuristic - BulutKlinik HTML degisirse bozulur) ===

    @staticmethod
    def _extract_title(html_text: str) -> str:
        m = re.search(r"<title[^>]*>(.*?)</title>", html_text,
                      re.IGNORECASE | re.DOTALL)
        return html.unescape(m.group(1).strip()) if m else ""

    @staticmethod
    def _extract_user_name(html_text: str) -> str:
        # Heuristic: user-name veya profile-name class'lı element
        for pat in (
            r'class="[^"]*(?:user-name|profile-name|user_full_name)[^"]*"[^>]*>([^<]+)<',
            r'data-user[^=]*="([^"]+)"',
            r'<span[^>]*id="userName"[^>]*>([^<]+)<',
        ):
            m = re.search(pat, html_text, re.IGNORECASE)
            if m:
                return html.unescape(m.group(1).strip())[:80]
        # Sayfa basliginda kullanici adi olabilir
        if "hakan" in html_text.lower()[:5000]:
            return "Hakan Yaz (heuristic)"
        return ""

    @staticmethod
    def _parse_patient_list(html_text: str, limit: int = 20) -> List[Dict]:
        # Generic: tr/td veya li/div ile satir parse
        out = []
        # Pattern 1: tabular - <tr> ... <td>name</td> ...
        for m in re.finditer(
                r'<tr[^>]*>(.*?)</tr>', html_text, re.DOTALL | re.IGNORECASE):
            row = m.group(1)
            tds = re.findall(r'<td[^>]*>(.*?)</td>', row,
                            re.DOTALL | re.IGNORECASE)
            if len(tds) >= 2:
                cleaned = [html.unescape(re.sub(r'<[^>]+>', '', t)).strip()
                          for t in tds[:6]]
                if cleaned[0] and len(cleaned[0]) < 100:
                    out.append({"cells": cleaned})
                    if len(out) >= limit:
                        break
        return out

    @staticmethod
    def _parse_appointment_list(html_text: str) -> List[Dict]:
        return BulutklinikCookieClient._parse_patient_list(html_text, limit=50)


# ============================================================================
# Module-level singleton + helper functions
# ============================================================================

_CLIENT: Optional[BulutklinikCookieClient] = None


def get_client() -> Optional[BulutklinikCookieClient]:
    global _CLIENT
    if _CLIENT is None:
        try:
            _CLIENT = BulutklinikCookieClient()
        except Exception:
            return None
    return _CLIENT


def reload_client() -> Optional[BulutklinikCookieClient]:
    """Cookie dosyasi guncellenince zorla yeniden yukle."""
    global _CLIENT
    _CLIENT = None
    return get_client()


def status() -> Dict[str, Any]:
    cl = get_client()
    if not cl:
        return {"ready": False, "error": "Cookie yok - bulutklinik_cookie_cdp.py calistir"}
    info = cl.session_info()
    if not info.get("exists"):
        return {"ready": False, "error": "Session dosyasi yok"}
    auth = cl.check_auth()
    return {
        "ready": auth,
        "cookies_count": info["cookies_count"],
        "age_hours": info["age_hours"],
        "expired": info["expired"],
        "source": info["source"],
        "auth_check": "OK" if auth else "FAIL - cookie expired",
    }


# ============================================================================
# CLI test
# ============================================================================

if __name__ == "__main__":
    import sys
    print("=" * 70)
    print("BULUTKLINIK COOKIE CLIENT TEST")
    print("=" * 70)
    cl = get_client()
    if not cl:
        print("\n[NO] Client olusturulamadi.")
        print("     Once: D:\\YazKlinik_Final_D500\\.venv\\Scripts\\python.exe "
              "D:\\YazKlinik_Final_D500\\bulutklinik_cookie_cdp.py")
        sys.exit(1)
    info = cl.session_info()
    print(f"\nSession: {info['cookies_count']} cookie, "
          f"{info['age_hours']} saat ({'EXPIRED' if info['expired'] else 'OK'})")
    print(f"\n[1] check_auth()...")
    ok = cl.check_auth(force=True)
    print(f"    {'OK - login aktif' if ok else 'FAIL - cookie expired'}")
    if not ok:
        sys.exit(1)
    print(f"\n[2] get_dashboard()...")
    try:
        d = cl.get_dashboard()
        print(f"    Title: {d['title']}")
        print(f"    User: {d['user_name']}")
        print(f"    HTML size: {d['size']} byte")
    except Exception as e:
        print(f"    HATA: {e}")
    print(f"\n[3] search_patients() heuristic test...")
    try:
        rows = cl.search_patients(limit=5)
        print(f"    {len(rows)} satir bulundu (path heuristic):")
        for r in rows[:3]:
            print(f"      {r}")
    except Exception as e:
        print(f"    HATA: {e}")
    print(f"\n[4] get_appointments_today() heuristic test...")
    try:
        rows = cl.get_appointments_today()
        print(f"    {len(rows)} satir")
    except Exception as e:
        print(f"    HATA: {e}")
    print()
