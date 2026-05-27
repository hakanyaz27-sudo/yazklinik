/**
 * YazKlinik - Cloudflare Worker (Free plan icin "Sistem bakimda" sayfasi)
 *
 * Neden: Free planda Custom Pages (500-class) kilitli (API error 1219).
 * Bu Worker, origin (yazhakan.com.tr -> tunnel -> 127.0.0.1:5443) cevap
 * veremediginde (502/503/504/520-527) ve istek bir SAYFA gezinmesi ise
 * dostane bakim sayfasini gosterir. Diger her sey (asset, API, WebSocket,
 * basarili cevaplar) hic dokunulmadan origin'e gecer.
 *
 * Format: klasik "service worker" (addEventListener) - hem panelden yapistirmaya
 * hem de API ile tek PUT'la yuklemeye uygundur.
 *
 * Kurulum (panel):
 *   Workers & Pages > Create application > Create Worker > kodu yapistir > Deploy
 *   Sonra: Worker > Settings > Domains & Routes (veya zone > Workers Routes) ->
 *   Route ekle: yazhakan.com.tr/*   ve   www.yazhakan.com.tr/*
 */

const MAINTENANCE_HTML = `<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta http-equiv="refresh" content="25">
<title>Sistem bakimda - YazKlinik</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
    background: linear-gradient(150deg, #0f766e 0%, #0ea5a4 55%, #134e4a 100%);
    color: #fff; padding: 24px;
  }
  .box {
    width: min(560px, 100%); background: rgba(255,255,255,.08);
    border: 1px solid rgba(255,255,255,.18); border-radius: 22px;
    padding: 40px 30px; text-align: center; backdrop-filter: blur(6px);
    box-shadow: 0 24px 60px rgba(0,0,0,.28);
  }
  .brand { font-size: 14px; font-weight: 800; letter-spacing: .12em; opacity: .85; text-transform: uppercase; }
  .spinner {
    width: 58px; height: 58px; margin: 22px auto 18px; border-radius: 50%;
    border: 5px solid rgba(255,255,255,.25); border-top-color: #fff;
    animation: spin 1s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  h1 { font-size: clamp(24px, 5vw, 34px); margin: 6px 0 10px; line-height: 1.15; }
  p { font-size: 16px; line-height: 1.6; opacity: .95; margin: 6px 0; }
  .small { font-size: 13px; opacity: .8; margin-top: 18px; }
  .pill { display:inline-block; margin-top:16px; background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.28);
          border-radius:999px; padding:8px 16px; font-weight:700; font-size:14px; }
</style>
</head>
<body>
  <div class="box">
    <div class="brand">YazKlinik</div>
    <div class="spinner" aria-hidden="true"></div>
    <h1>Sistem kisa bir bakimda</h1>
    <p>Sayfa birkac dakika icinde tekrar hazir olacak.</p>
    <p>Lutfen <b>5 dakika sonra</b> tekrar deneyin.</p>
    <div class="pill">Bu sayfa otomatik yenilenir</div>
    <div class="small">Acil durumda klinigi telefonla arayabilirsiniz.</div>
  </div>
</body>
</html>`;

// Origin "ayakta degil" sayilan durumlar (host/tunnel hatalari).
const DOWN_STATUSES = new Set([502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527, 530]);

function isPageNavigation(request) {
  if (request.method !== "GET") return false;
  const dest = request.headers.get("Sec-Fetch-Dest") || "";
  if (dest === "document") return true;
  const accept = request.headers.get("Accept") || "";
  return accept.includes("text/html");
}

function maintenanceResponse() {
  return new Response(MAINTENANCE_HTML, {
    status: 503,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store, no-cache, must-revalidate",
      "Retry-After": "120",
    },
  });
}

async function handle(request) {
  let response;
  try {
    response = await fetch(request);
  } catch (err) {
    // Origin'e hic ulasilamadi.
    return isPageNavigation(request)
      ? maintenanceResponse()
      : new Response("Origin unreachable", { status: 502 });
  }

  if (DOWN_STATUSES.has(response.status) && isPageNavigation(request)) {
    return maintenanceResponse();
  }
  // Normal trafik / asset / API / WebSocket / basarili cevap: dokunma.
  return response;
}

addEventListener("fetch", (event) => {
  event.respondWith(handle(event.request));
});
