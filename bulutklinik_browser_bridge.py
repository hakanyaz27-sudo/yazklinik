"""BulutKlinik browser bridge - bir kez login, gunlerce otomatik.

Akis:
  1) Headed Chromium aciliyor (server PC ekraninda gorulur)
  2) Email + sifre otomatik doluyor
  3) Sen sadece captcha + SMS'i elinle yapiyorsun
  4) Login sonrasi cookies/storage kaydediliyor (bulutklinik_session.json)
  5) Sonraki calistirmada cookie ile otomatik baglan, captcha YOK
  6) Cookie'ler 24-72 saat gecerli (Bulutklinik politikasina gore)

Kullanim:
  python bulutklinik_browser_bridge.py            # interaktif login + sakla
  python bulutklinik_browser_bridge.py --check    # session gecerli mi
  python bulutklinik_browser_bridge.py --auto     # cookie ile otomatik test
"""
from __future__ import annotations
import os, sys, json, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = "https://app.bulutklinik.com"
LOGIN_URL = f"{BASE}/Login"
EMAIL = "hakanyaz27@gmail.com"
PW = "Klinik796."
SESSION_FILE = r"D:\YazKlinik_Final_D500\bulutklinik_session.json"

from playwright.sync_api import sync_playwright


def interactive_login():
    """Headed browser, email/pass auto-fill, kullanici captcha+SMS coz."""
    print("=" * 70)
    print("BULUTKLINIK BROWSER BRIDGE - INTERAKTIF LOGIN")
    print("=" * 70)
    print("\n1. Bir Chromium penceresi acilacak (gorebilirsen ekranda)")
    print("2. Email + sifre OTOMATIK doldurulacak")
    print("3. SEN sadece:")
    print("   - reCAPTCHA kutusunu isaretle")
    print("   - 'Sisteme Giris' butonuna bas")
    print("   - SMS kodunu girip 'Gonder' bas")
    print("4. Login OK olunca cookie kaydedilir, otomatik kapanir\n")
    input("Hazirsan ENTER'a bas...")

    with sync_playwright() as p:
        # D700: Sistemde kurulu Google Chrome'u kullan (Playwright'in
        # indirdigi binary bazen path sorunu yapiyor). Chrome yoksa
        # default Chromium'a dus.
        launch_kwargs = {"headless": False, "args": ["--start-maximized"]}
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        import os as _os
        for cp in chrome_paths:
            if _os.path.exists(cp):
                launch_kwargs["executable_path"] = cp
                if "msedge" in cp:
                    launch_kwargs["channel"] = "msedge"
                print(f"[BROWSER] Sistem browser: {cp}")
                break
        try:
            browser = p.chromium.launch(**launch_kwargs)
        except Exception as ex:
            print(f"[ERR] Sistem browser acilamadi: {ex}")
            print("[BROWSER] Playwright default Chromium deneniyor...")
            browser = p.chromium.launch(headless=False,
                                        args=["--start-maximized"])
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 Chrome/124.0",
            locale="tr-TR",
            viewport={"width": 1400, "height": 900})
        page = ctx.new_page()

        print(f"\n[BROWSER] {LOGIN_URL}'a gidiliyor...")
        page.goto(LOGIN_URL, timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        # E-posta + sifre doldur
        print("[BROWSER] Email + sifre dolduruluyor...")
        try:
            page.fill('input[name="email"]', EMAIL)
            page.fill('input[name="password"]', PW)
            print(f"[BROWSER] OK: email={EMAIL}, password=*** dolu")
        except Exception as e:
            print(f"[HATA] Form alanlari bulunamadi: {e}")
            input("Devam etmek icin ENTER...")

        print("\n>>> SIRA SENDE <<<")
        print("  1) reCAPTCHA isaretle (varsa)")
        print("  2) 'Sisteme Giris' tikla")
        print("  3) SMS kodu gir (telefonuna geldiginde) -> Gonder")
        print("  4) Ana sayfa acildiginda BURAYA DON ve ENTER BAS")
        print("     (Otomatik tespit cogu zaman calismaz - manuel ENTER en garanti yol)\n")

        # Manuel ENTER yontemi - URL detection guvenilmez
        input(">>> Login tamamlandiysa ENTER bas (cookie kaydedilir) <<<")
        cur = page.url
        print(f"\n[BROWSER] Mevcut URL: {cur}")
        if "/Login" in cur:
            print("[WARN] Hala /Login sayfasinda - login basarili olmadi mi?")
            print("       Yine de cookie alinacak (varsa).")

        # Cookies + storage sakla
        cookies = ctx.cookies()
        storage = ctx.storage_state()
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "saved_at": int(time.time()),
                "url_at_save": page.url,
                "cookies_count": len(cookies),
                "storage_state": storage,
            }, f, indent=2)
        print(f"\n[OK] Session kaydedildi: {SESSION_FILE}")
        print(f"     {len(cookies)} cookie, login URL: {page.url}")
        print(f"\n>>> Tarayicida son durum: {page.title()}")
        time.sleep(3)
        browser.close()


def check_session():
    """Kayitli session var mi + ne kadar eski."""
    if not os.path.exists(SESSION_FILE):
        print(f"[NO] Session dosyasi yok: {SESSION_FILE}")
        return False
    with open(SESSION_FILE, "r", encoding="utf-8") as f:
        d = json.load(f)
    age_h = (time.time() - d["saved_at"]) / 3600
    print(f"[OK] Session var ({d['cookies_count']} cookie)")
    print(f"     Yas: {age_h:.1f} saat")
    print(f"     URL: {d.get('url_at_save')}")
    if age_h > 72:
        print("[WARN] 72 saatten eski - tekrar login gerekebilir")
    return True


def auto_session_test():
    """Kayitli cookie ile aciliyor mu test."""
    if not os.path.exists(SESSION_FILE):
        print("[NO] Once interactive_login() calistir.")
        return
    with open(SESSION_FILE, "r", encoding="utf-8") as f:
        d = json.load(f)
    storage_state = d.get("storage_state")
    if not storage_state:
        print("[NO] Storage state yok, tekrar login gerek.")
        return
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(storage_state=storage_state,
                                  viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        print("[AUTO] Anasayfa aciliyor (saved session ile)...")
        page.goto(BASE + "/", timeout=20000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        cur = page.url
        title = page.title()
        print(f"  URL: {cur}")
        print(f"  Title: {title}")
        if "/Login" in cur:
            print("[FAIL] Session expire olmus, tekrar interactive_login() gerek.")
        else:
            print("[OK] Session aktif, otomatik giris basarili.")
        input("Tarayiciyi kapatmak icin ENTER...")
        browser.close()


def main():
    if "--check" in sys.argv:
        check_session()
    elif "--auto" in sys.argv:
        auto_session_test()
    else:
        if check_session():
            print("\nMevcut session var. Yine de yeni login yapayim mi? (y/N): ", end="")
            ans = input().strip().lower()
            if ans != "y":
                print("Iptal."); return
        interactive_login()


if __name__ == "__main__":
    main()

