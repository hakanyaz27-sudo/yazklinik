"""YazKlinik D250 production smoke test.

Checks the live local server like a user would: login, critical pages,
static GET routes, key API endpoints, and broken 500/404 responses. This
script intentionally avoids destructive POST actions.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path


BASE_URL = os.environ.get("YAZKLINIK_TEST_BASE_URL", "https://127.0.0.1:5443")
USERNAME = os.environ.get("YAZKLINIK_TEST_USER", "doktor")
PASSWORD = os.environ.get("YAZKLINIK_TEST_PASSWORD", "1234")
ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "yazklinik_web.py"

CRITICAL_PATHS = [
    "/",
    "/dashboard",
    "/hastalar",
    "/randevular",
    "/ses-ve-alex",
    "/akilli-dialog",
    "/sessiz-alex",
    "/sohbet-merkezi",
    "/ajanlar",
    "/sesli-recete",
    "/yz-ses-cevir",
    "/ses-profilleri",
    "/mikrofon-tani",
    "/yz-telefon-diyalog",
    "/onam-sablonlari",
    "/tedavi-planla",
    "/diyet-rehberi",
    "/ivf-konsult",
    "/dicom",
    "/sistem-ayarlari",
    "/ayarlar",
    "/tum-ayarlar",
    "/sistem-durumu",
    "/api/sistem-durumu",
    "/api/alex/qa",
]


class SmokeError(RuntimeError):
    pass


def _opener() -> urllib.request.OpenerDirector:
    jar = CookieJar()
    handlers = [urllib.request.HTTPCookieProcessor(jar)]
    if BASE_URL.lower().startswith("https://"):
        handlers.append(
            urllib.request.HTTPSHandler(
                context=ssl._create_unverified_context()))
    return urllib.request.build_opener(*handlers)


def _request(opener: urllib.request.OpenerDirector, path: str, timeout: int = 18):
    url = BASE_URL.rstrip("/") + path
    try:
        with opener.open(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), str(resp.geturl())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace"), url
    except Exception as exc:
        return "ERR", str(exc), url


def _login(opener: urllib.request.OpenerDirector) -> None:
    form = urllib.parse.urlencode({
        "username": USERNAME,
        "password": PASSWORD,
    }).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL.rstrip("/") + "/giris",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with opener.open(req, timeout=15) as resp:
            if resp.status not in (200, 302):
                raise SmokeError(f"LOGIN_FAILED status={resp.status}")
    except urllib.error.HTTPError as exc:
        if exc.code not in (200, 302):
            raise SmokeError(f"LOGIN_FAILED status={exc.code}") from exc


def _static_get_routes() -> list[str]:
    text = SOURCE.read_text(encoding="utf-8", errors="replace")
    routes: list[str] = []
    pattern = re.compile(r'@app\.route\("([^"]+)"(?:,\s*methods=\[([^\]]+)\])?')
    for match in pattern.finditer(text):
        route = match.group(1)
        methods = match.group(2) or ""
        if "<" in route or "{" in route:
            continue
        if "POST" in methods and "GET" not in methods:
            continue
        if route.startswith(("/static/", "/uploads/")):
            continue
        if route not in routes:
            routes.append(route)
    return routes


def _scrape_local_links(html: str) -> list[str]:
    links: list[str] = []
    for href in re.findall(r"href=[\"']([^\"'#?]+)", html or ""):
        if not href.startswith("/") or href.startswith("//"):
            continue
        if any(skip in href for skip in ("/hasta/", "/dosya/", "/static/", "/uploads/", "/api/")):
            continue
        if "<" not in href and href not in links:
            links.append(href)
    return links


def main() -> int:
    opener = _opener()
    _login(opener)

    paths: list[str] = []
    for path in CRITICAL_PATHS + _static_get_routes():
        if path not in paths:
            paths.append(path)

    issues = []
    timings = []
    checked = []
    index = 0
    while index < len(paths) and len(checked) < 320:
        path = paths[index]
        index += 1
        if path in checked:
            continue
        checked.append(path)
        started = time.time()
        status, body, final_url = _request(opener, path)
        seconds = time.time() - started
        timings.append((seconds, path, status, len(body or "")))
        if status == "ERR" or (isinstance(status, int) and status >= 500):
            issues.append({
                "path": path,
                "status": status,
                "seconds": round(seconds, 2),
                "note": str(body)[:220],
            })
        elif isinstance(status, int) and status == 404 and not path.startswith("/api/"):
            issues.append({
                "path": path,
                "status": status,
                "seconds": round(seconds, 2),
                "note": "404",
            })
        if path in CRITICAL_PATHS and isinstance(status, int) and status == 200:
            for link in _scrape_local_links(body):
                if link not in paths:
                    paths.append(link)

    slowest = [
        {
            "seconds": round(seconds, 2),
            "path": path,
            "status": status,
            "bytes": length,
        }
        for seconds, path, status, length in sorted(timings, reverse=True)[:20]
    ]
    report = {
        "checked": len(checked),
        "issues": issues,
        "slowest": slowest,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if issues:
        raise SmokeError(f"PRODUCTION_SMOKE_ISSUES={len(issues)}")
    print("D250_PRODUCTION_SMOKE_OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"D250_PRODUCTION_SMOKE_FAIL: {exc}")
        raise SystemExit(1)
