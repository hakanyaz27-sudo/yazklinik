# Codex - Basla Buradan

Klasor:

```text
D:\YazKlinik_Final_D300
```

Bu D300 surumu, D200 son calisan halinden uretilmis yeni calisma kopyasidir.
Ilk is olarak `AGENTS.md` ve `D300_HANDOFF.md` oku.

## Komutlar

Baslat:

```powershell
D:\YazKlinik_Final_D300\D300_BASLAT.bat
```

Test:

```powershell
Set-Location "D:\YazKlinik_Final_D300"
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" -m py_compile yazklinik_web.py yazklinik_v68.py yazklinik_feature_sync.py D300_TERMINAL_SYNC.py
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" CODEX_QUICK_CHECK.py
```

Beklenen:

```text
CODEX_D300_QUICK_CHECK_OK
```

## Son degisiklikler

- **2026-05-16 (aksam):** Uzaktan erisim altyapisi + Alex SIP bridge entegre edildi. Detayli handoff: **`CODEX_HANDOFF_2026-05-16_SESSION3.md`**.
    - Claude: `yazklinik_remote_access.py` (ProxyFix + audit) + `TAILSCALE_UZAKTAN_ERISIM.md` (kurulum rehberi). Public IP 176.236.92.142:65187 / Tailscale Funnel ikinci PC'den koprulenir.
    - Codex: `yazklinik_sip_alex_client.py` (SIP bridge), `D300_SERVICE_RUNNER.py`, `D300_SIP_ALEX_BASLAT.bat` (sessiz baslatma).
    - **P0 ACIL:** default `doktor/1234` parolayi degistir (`/sifre-degistir`) - public IP acildi.
    - **P1 NEXT:** SIP bridge gelen cagri handler'ina `yazklinik_telesekreter_agent.parse_call()` wire et.
- **2026-05-16 (ogleden sonra):** 3 yeni ajan + 1 buyuk fix + 2 UX iyilestirme. Detayli handoff: **`CODEX_HANDOFF_2026-05-16_SESSION2.md`**.
    - YZ Konsultasyon ajani (`/yz-konsultasyon`) - 5-step OB-GYN klinik karar destek
    - Tibbi Ceviri ajani (`/ceviri-merkezi`) - PubMed + qwen2.5:32b yerel
    - Instagram Hazirlik ajani (`/instagram-hazirla`) - USG arsivinden KVKK-anonim draft
    - **fix(voluson):** USG PDF importu artik yas/kilo/boy/TA/LMP de visits + patient_demographics'a yazar
    - Medikal tema CSS overlay (additive)
    - Alex bar suruklenebilir + 9 preset + Alt+A/M/C kisayollari
    - MANIFEST_VERSION -> 2026.05.16-D300-AGENTS-IG-CEVIRI-KONSULT
- **2026-05-16 (sabah):** 10 klinik ajan eklendi (telesekreter / sesli onay / USG rapor / geri cagirma / BK sync bekci / NAS izleyici / recete / gunluk ozet / mojibake bekci / PR reviewer). `/ajanlar` dashboard + `/api/agents/*` Blueprint. Detayli handoff: **`CODEX_HANDOFF_2026-05-16_AJANLAR.md`**. v68 ve mevcut route'lar dokunulmadi.
- WebShell hizli Chrome/Edge app-mode kabuga tasindi.
- WebShell fast-mode algilamasi user-agent ve `yk_webshell=1` ile garanti edildi.
- Mod secimi ve tema secimi ust menude tekrar calisir.
- D300 config, DB ve backup yollari ayrildi.


