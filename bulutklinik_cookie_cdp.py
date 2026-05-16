"""Chrome'u --remote-debugging-port ile baslat + Playwright CDP ile cookies cek.

App-Bound Encryption'i bypass eder cunku Chrome'un kendisi ile konusur,
disardan decrypt etmez.

Akis:
  1) Mevcut tum Chrome'lari KAPAT (zorunlu)
  2) Bu script Chrome'u --remote-debugging-port=9222 ile baslatir
  3) Senin profillenin acilir (Default - login olduguin yer)
  4) BulutKlinik'a git, login degilsen login ol
  5) CMD'ye don, ENTER bas
  6) Cookies cekilir + sakliyor
"""
from __future__ import annotations
import os, sys, io, json, time, subprocess

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
# D300 v2: Gecici profile - Chrome kendi profilinde debug port acmiyor.
# Bu klasor BulutKlinik icin ozel, baska Chrome'lari etkilemez.
USER_DATA = r"D:\YazKlinik_Final_D300\bulutklinik_browser_profile"
DEBUG_PORT = 9222
SESSION_FILE = r"D:\YazKlinik_Final_D300\bulutklinik_session.json"
TARGET_URL = "https://app.bulutklinik.com/App/My/favorites.gg"
DOMAIN = "bulutklinik.com"


def main():
    if not os.path.exists(CHROME):
        print(f"HATA: Chrome bulunamadi: {CHROME}")
        sys.exit(1)

    print("=" * 70)
    print("CHROME CDP COOKIE IMPORT")
    print("=" * 70)
    print(f"\n>>> ONEMLI: Tum Chrome pencerelerini KAPAT! <<<")
    print(f"    (Task Manager > Chrome > End Task gerekirse)\n")
    input("Hazirsan ENTER...")

    # Once mevcut Chrome'lari oldur (yoksa debug port'u aktiflesmez)
    print("\n[CHROME] Mevcut Chrome process'leri kontrol ediliyor...")
    try:
        ts_out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
            capture_output=True, text=True, timeout=5)
        if "chrome.exe" in (ts_out.stdout or "").lower():
            print("  *** UYARI: Chrome zaten calisiyor ***")
            print("  Lutfen TUM Chrome pencerelerini KAPAT, sonra:")
            print("    Get-Process chrome | Stop-Process -Force")
            print("  veya Task Manager > Chrome > End Task")
            input("  Chrome'u kapatip ENTER bas...")
    except Exception:
        pass

    # Chrome'u debug portu ile baslat - SENIN profilinde
    print(f"\n[CHROME] --remote-debugging-port={DEBUG_PORT} ile baslatiliyor...")
    proc = subprocess.Popen([
        CHROME,
        f"--remote-debugging-port={DEBUG_PORT}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={USER_DATA}",
        "--no-first-run",
        "--no-default-browser-check",
        TARGET_URL,
    ])
    print(f"  PID: {proc.pid}")

    # Port'un acilmasini bekle
    import socket
    print(f"  Port {DEBUG_PORT} acilmasi bekleniyor...")
    for i in range(20):  # 10 saniye
        time.sleep(0.5)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect(("127.0.0.1", DEBUG_PORT))
            s.close()
            print(f"  Port AKTIF (denenmis: {i+1})")
            break
        except Exception:
            continue
    else:
        print(f"  *** Port hala acilmadi - Chrome debug acmayi reddetti ***")
        print(f"  Sebep: muhtemelen Chrome zaten acikti, yeni instance acmadi.")
        sys.exit(1)
    print(f"\n>>> SIRA SENDE <<<")
    print(f"  1) Acilan Chrome'da BulutKlinik gozukmeli")
    print(f"     Eger login degilsen: login + captcha + SMS yap")
    print(f"     Eger zaten login: anasayfa veya favorites gozukmeli")
    print(f"  2) Hazir olunca buraya don, ENTER bas\n")
    input(">>> Chrome'da BulutKlinik aciksa ENTER bas <<<")

    # Playwright CDP ile bagla, cookies cek
    print("\n[CDP] Chrome'a CDP ile baglaniyor (127.0.0.1, IPv4)...")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(
                f"http://127.0.0.1:{DEBUG_PORT}")
        except Exception as exc:
            print(f"  CDP HATA: {exc}")
            print(f"  Chrome --remote-debugging-port'la basladi mi?")
            sys.exit(1)
        # Tum context'lere bak
        all_cookies = []
        for ctx in browser.contexts:
            cookies = ctx.cookies()
            for c in cookies:
                if DOMAIN in (c.get("domain") or ""):
                    all_cookies.append(c)
            for page in ctx.pages:
                print(f"  Page: {page.url[:80]}")
        print(f"\n  Bulunan {DOMAIN} cookie sayisi: {len(all_cookies)}")
        for c in all_cookies[:10]:
            v = (c.get("value") or "")[:30]
            print(f"    {c['name']}={v}... (domain={c.get('domain')})")
        if not all_cookies:
            print("\n*** HATA: Hicbir bulutklinik cookie yok ***")
            print("    BulutKlinik'a login degilsin demek.")
            print("    Chrome'u acik birak, login yap, scripti tekrar calistir.")
            browser.close()
            sys.exit(1)

        # Test: cookies ile favorites.gg cek
        print(f"\n[TEST] Cookies ile {TARGET_URL}...")
        import requests
        s = requests.Session()
        for c in all_cookies:
            try:
                s.cookies.set(c["name"], c["value"],
                              domain=c["domain"], path=c.get("path", "/"))
            except Exception:
                pass
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 Chrome/124.0",
        })
        r = s.get(TARGET_URL, timeout=15, allow_redirects=True)
        print(f"  HTTP {r.status_code}, Final URL: {r.url}")
        is_login = "/Login" in r.url
        if is_login:
            print(f"  *** Login sayfasina yonlendirildi (cookie expired?) ***")
        else:
            print(f"  OK - Sayfa {len(r.text)} byte")
            if "hakan" in r.text.lower() or "yaz" in r.text.lower():
                print(f"  ✓ Profile ismi sayfada bulundu")

        # Sakla (Playwright storage_state formatinda)
        storage_state = {"cookies": all_cookies, "origins": []}
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "saved_at": int(time.time()),
                "url_at_save": TARGET_URL,
                "cookies_count": len(all_cookies),
                "storage_state": storage_state,
                "source": "chrome-cdp-import",
                "raw_cookies": all_cookies,
                "login_works": not is_login,
            }, f, indent=2, ensure_ascii=False)
        print(f"\n[OK] Kaydedildi: {SESSION_FILE}")
        browser.close()

    print("\nChrome'u kapatabilirsin. yazklinik bu cookie ile bagli.")


if __name__ == "__main__":
    main()
