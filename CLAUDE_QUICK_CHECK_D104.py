from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import py_compile
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def ok(label: str) -> None:
    print(f"PASS: {label}")


def fail(label: str, detail: str = "") -> None:
    message = f"FAIL: {label}"
    if detail:
        message += f" - {detail}"
    print(message)
    raise SystemExit(1)


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def must_exist(rel: str) -> None:
    path = ROOT / rel
    if not path.exists():
        fail("missing file", rel)
    ok(f"exists {rel}")


def must_contain(rel: str, needle: str) -> None:
    text = read(rel)
    if needle not in text:
        fail(f"{rel} marker missing", needle)
    ok(f"{rel} contains {needle}")


def compile_file(rel: str) -> None:
    path = ROOT / rel
    if not path.exists():
        fail("compile target missing", rel)
    pycache = Path(tempfile.gettempdir()) / "yk_d104_claude_pycache"
    pycache.mkdir(parents=True, exist_ok=True)
    old_env = os.environ.get("PYTHONPYCACHEPREFIX")
    old_prefix = getattr(sys, "pycache_prefix", None)
    os.environ["PYTHONPYCACHEPREFIX"] = str(pycache)
    sys.pycache_prefix = str(pycache)
    try:
        py_compile.compile(str(path), doraise=True)
    except Exception as exc:
        fail(f"compile {rel}", str(exc))
    finally:
        sys.pycache_prefix = old_prefix
        if old_env is None:
            os.environ.pop("PYTHONPYCACHEPREFIX", None)
        else:
            os.environ["PYTHONPYCACHEPREFIX"] = old_env
    ok(f"compile {rel}")


def http_json(opener: urllib.request.OpenerDirector, url: str, data: dict[str, str] | None = None) -> dict:
    encoded = None
    headers = {"Accept": "application/json"}
    if data is not None:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=encoded, headers=headers)
    with opener.open(req, timeout=25) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(body)
    except Exception:
        return {"_raw": body}


def live_check(base_url: str) -> None:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    login_url = base_url.rstrip("/") + "/giris"
    req = urllib.request.Request(
        login_url,
        data=urllib.parse.urlencode({"username": "doktor", "password": "1234"}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with opener.open(req, timeout=30) as resp:
        if resp.status not in (200, 302):
            fail("live login", str(resp.status))
    ok("live login")

    tests = [
        ("medication", "mo"),
        ("medication", "du"),
        ("diagnosis", "va"),
        ("diagnosis", "ge"),
    ]
    for kind, query in tests:
        url = (
            base_url.rstrip()
            + "/api/recete-katalog-ara?"
            + urllib.parse.urlencode({"kind": kind, "q": query, "limit": "12"})
        )
        started = time.perf_counter()
        payload = http_json(opener, url)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if not payload.get("ok"):
            fail(f"live catalog {kind}:{query}", str(payload)[:300])
        if int(payload.get("count") or 0) <= 0:
            fail(f"live catalog empty {kind}:{query}")
        ok(f"live catalog {kind}:{query} count={payload.get('count')} ms={elapsed_ms}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Check running D104 server on 127.0.0.1:5052")
    parser.add_argument("--base-url", default="http://127.0.0.1:5052")
    args = parser.parse_args()

    for rel in [
        "CLAUDE.md",
        "CLAUDE_BASLA_BURADAN_D104.md",
        "CLAUDE_PROMPT_D104.txt",
        "AGENTS.md",
        "yazklinik_web.py",
        "yazklinik_desktop_v1000.py",
        "yazklinik_feature_sync.py",
    ]:
        must_exist(rel)

    for rel in [
        "yazklinik_web.py",
        "yazklinik_desktop_v1000.py",
        "yazklinik_feature_sync.py",
    ]:
        compile_file(rel)

    must_contain("yazklinik_web.py", "def _rx_catalog_score")
    must_contain("yazklinik_web.py", "function showRowMedicationHints")
    must_contain("yazklinik_web.py", "function scheduleMedicationSearch(query, targetInput)")
    must_contain("yazklinik_web.py", 'limit: "160"')
    must_contain("yazklinik_web.py", 'list="ykRxMedicationCatalog"')
    must_contain("yazklinik_desktop_v1000.py", '("Recete", "/hasta/{patient}/recete-hazirla", False)')
    must_contain("yazklinik_desktop_v1000.py", 'add_button(3, 0, "Recete"')
    must_contain("yazklinik_feature_sync.py", "2026.05.09-D128-PERF-VOICE-BRAND-INSTANT")
    must_contain("CLAUDE.md", "YazKlinik Final D128")

    if args.live:
        live_check(args.base_url)

    print("CLAUDE_D104_QUICK_CHECK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
