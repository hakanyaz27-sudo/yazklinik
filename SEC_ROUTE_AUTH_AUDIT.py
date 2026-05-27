# -*- coding: utf-8 -*-
"""SEC_ROUTE_AUTH_AUDIT - @app.route'lari tarar; HASSAS olup @login_required (veya
benzeri auth) olmayan rotalari isaretler. Internete acik klinik icin KVKK/yetkisiz
erisim riski. Sadece RAPOR uretir (read-only)."""
import re

SRC = "yazklinik_web.py"
lines = open(SRC, encoding="utf-8", errors="replace").read().splitlines()

# Bilerek public olan / auth gerekmeyen kaliplar
PUBLIC_OK = (
    "/giris", "/login", "/logout", "/cikis", "/static", "/favicon",
    "/manifest", "/saglik", "/health", "/api/terminal/ping", "/robots",
    "/hasta-portal", "/portal", "/.well-known", "/sw.js", "/service-worker",
    "/api/phone/ai-webhook",  # secret-token ile korunuyor
    "/yk-", "/api/web-mic", "/api/cron",  # cron token ile
)
# Hassas sinyaller (yetkisizse kritik)
SENSITIVE = ("hasta", "patient", "randevu", "gebelik", "tahlil", "recete",
             "dosya", "klinik-form", "usg", "dicom", "diyet", "rapor",
             "ayarlar", "admin", "yedek", "backup", "audit", "kullanici")
AUTH_MARKERS = ("login_required", "_required", "abort(401", "abort(403",
                "_is_local_browser_request_a100", "session.get")

routes = []
i = 0
n = len(lines)
while i < n:
    if lines[i].lstrip().startswith("@app.route"):
        block = []
        paths = []
        j = i
        # tum ardisik decorator + route'lari topla, def'e kadar
        while j < n and not lines[j].lstrip().startswith("def "):
            block.append(lines[j])
            m = re.search(r"@app\.route\(\s*['\"]([^'\"]+)['\"]", lines[j])
            if m:
                paths.append(m.group(1))
            j += 1
        defname = ""
        if j < n:
            dm = re.search(r"def\s+(\w+)", lines[j])
            defname = dm.group(1) if dm else ""
        block_txt = "\n".join(block)
        # def govdesinin ilk ~6 satirinda da auth kontrolu olabilir
        body_head = "\n".join(lines[j:j + 8])
        has_auth = any(mk in block_txt for mk in AUTH_MARKERS) or \
            any(mk in body_head for mk in ("abort(401", "abort(403",
                                           "_is_local_browser_request_a100"))
        for p in paths:
            pl = p.lower()
            is_public = any(pl.startswith(x) or x in pl for x in PUBLIC_OK)
            is_sensitive = any(s in pl for s in SENSITIVE)
            routes.append({
                "path": p, "def": defname, "auth": has_auth,
                "public": is_public, "sensitive": is_sensitive,
                "line": i + 1,
            })
        i = j
    else:
        i += 1

total = len(routes)
flagged = [r for r in routes
           if (not r["auth"]) and r["sensitive"] and (not r["public"])]
print(f"Toplam route kaydi: {total}")
print(f"HASSAS + AUTH YOK + public-degil: {len(flagged)}")
print("-" * 72)
for r in flagged[:60]:
    print(f"  L{r['line']:>6}  {r['path']:45} -> {r['def']}")
print("-" * 72)
print("Not: 'auth yok' = decorator/govde basinda login_required veya benzeri")
print("isaret bulunamadi demek; manuel teyit gerekir (kimi rota iceride kontrol")
print("ediyor olabilir).")
