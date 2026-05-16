# CODEX_FILE_MAP.md - Dosya sorumluluklari

## Ana modul (D:\YazKlinik_Final_D300\)

| Dosya | Boyut | Sorumluluk | Dokun? |
|---|---|---|---|
| `yazklinik_web.py` | ~6.8 MB | **Ana Flask uygulamasi** - tum route, UI, is mantigi | âœ… EVET (dikkatli) |
| `yazklinik_v68.py` | ~3 MB | Legacy monolit - DB schema, helper, model. ~8000 satir | âš  DOKUNMA (mecbur kalirsan kucuk) |
| `yazklinik_feature_sync.py` | ~50 KB | Sidebar route manifesti (web + desktop + WebShell uyumlu) | âœ… EVET |
| `yazklinik_desktop_v1000.py` | ~150 KB | Windows hybrid PySide6 desktop shell | âš  Sadece UI degisiklik |
| `yazklinik_textfix.py` | ~5 KB | Mojibake fix (`fix_mojibake_text`) | âœ… EVET |
| `yazklinik_config.py` | ~10 KB | `load_config()` / `save_config()` JSON | âœ… EVET |
| `yazklinik_common.py` | ~20 KB | `get_active_patient`, `set_active_patient` | âœ… EVET |
| `yazklinik_db_onar.py` | ~5 KB | DB onarim + WAL recovery | âš  Dikkat |
| `yazklinik_dicom_private.py` | ~30 KB | DICOM Private Tag parser (Voluson) | âœ… EVET |
| `yazklinik_enabiz_agent.py` | ~15 KB | E-Nabiz entegrasyon | âœ… EVET |
| `yazklinik_integration_agents.py` | ~25 KB | YZ provider'lar (Ollama/OpenAI/Gemini/Groq) | âœ… EVET |
| `yazklinik_nas_watcher.py` | ~10 KB | NAS klasor degisiklik dinleyici thread | âš  Dikkat |
| `yazklinik_open_folder_helper.py` | ~3 KB | Windows klasor explorer ile ac | âœ… EVET |
| `yazklinik_pdf_patient_extract.py` | ~20 KB | PDF -> hasta meta data | âœ… EVET |
| `yazklinik_photo_print_helper.py` | ~5 KB | 6x8 foto print | âœ… EVET |
| `yazklinik_runtime_cleanup.py` | ~3 KB | Eski dosya temizlik | âœ… EVET |
| `yazklinik_updater.py` | ~10 KB | Otomatik guncelleyici | âš  Dikkat |
| `yazklinik_whatsapp_local_helper.py` | ~5 KB | WhatsApp Web entegre | âœ… EVET |

## Klasorler

| Klasor | Icerik | Dokun? |
|---|---|---|
| `yazklinik\` | Python paketi - sub-moduller | âš  Dikkat |
| `static\` | CSS/JS/img - UI varlik | âœ… EVET |
| `tools\` | Yan araclar (PDF/OCR/imageio-ffmpeg) | âš  Dikkat |
| `local_db\` | **LOKAL SQLITE DB** | âš  ASLA SILME |
| `auto_backups\` | 24 saatte bir DB yedek | âš  Eski yedek silinebilir |

## Dokuman + ayar

| Dosya | Ne |
|---|---|
| `AGENTS.md` | Codex / OpenAI agent ana brief (Turkce) |
| `README_D300.md` | Tam dokumantasyon |
| `CODEX_QUICK_CHECK.py` | Sistem durumu dogrulama |
| `CODEX_FILE_MAP.md` | Bu dosya |
| `CODEX_COMMANDS.md` | Yaygin komutlar |
| `CODEX_API_ENDPOINTS.md` | Flask route listesi |
| `config.env` | â˜… Tum ayarlar (NAS, DB, port) - HAS COMMENTS |
| `D300_BASLAT.bat` | â˜… Tek tikla launcher |

## yazklinik_web.py Bolumleri (line araliklari)

> Bu dosya 130k+ satir. Editlerken yakin route'larin bolumune bak.

| Line | Bolum |
|---|---|
| 1-700 | Import, sabitler, helper'lar |
| 700-2500 | `_db_get_setting`, `cache_*`, `db_conn` wrapper |
| 2500-9000 | YZ entegre + smart dialog + Alex |
| 9000-13000 | OB/GYN clinical helpers (gebelik, USG hesap) |
| 13000-15000 | DB + cache yardimcilar |
| 15000-25000 | Hasta dosyasi UI route'lar |
| 25000-44000 | Hasta yonetimi (kayit, sil, arsivle) |
| 44000-46500 | Login, ana home (`/hastalar`) |
| 46500-62000 | Hasta dosya icerik route'lar (USG, PDF, lab) |
| 62000-63000 | DDI rules + tedavi protokol |
| 63000-64000 | `/tedavi-planla` + A5 recete + `/hasta-birlestir` + `/sistem-ayarlari` |
| 64000-67000 | Diet rehber + obgyn rehber |
| 67000-90000 | Diger klinik moduller |
| 90000-130000+ | UI helpers, WhatsApp, raporlar |

## DB Tablo Sorumluluklari

| Tablo | Ne | Dokun? |
|---|---|---|
| `patients` | Hasta ana kayit (folder_key PK) | âš  archived_at set, silme |
| `patient_protocols` | Protokol no (patient_key FK) | âš  Dikkat |
| `patient_demographics` | Yas/kilo/SAT (data_json JSON) | âœ… Update OK |
| `visits` | Hasta gelisleri | âš  archived_at OK |
| `files` | PDF/JPG dosya kayit (NAS path) | âš  Dikkat |
| `usg_measurements` | GA/BPD/HC/AC/FL | âš  Dikkat |
| `prescriptions` | Recete | âœ… Insert/Update OK |
| `web_audit_log` | Islem audit | âœ… Insert OK |
| `settings` | KEY-VALUE app ayarlari | âœ… EVET |
| `sysparams` | Sistem parametreleri | âœ… EVET |

## Dikkat edilmesi gereken pattern'ler

### 1. Inline HTML/JS in Python f-string
```python
content = f"""
<style>
.foo {{ color: red; }}   <!-- Cift brace cunku f-string -->
</style>
<script>
function bar() {{ alert('X'); }}
</script>
"""
```

### 2. db_conn() context manager
```python
with db_conn() as con:
    con.row_factory = lambda cur, row: {
        d[0]: row[i] for i, d in enumerate(cur.description)}
    rows = con.execute("SELECT * FROM patients LIMIT 5").fetchall()
```

### 3. Cache pattern
```python
cache_key = f"my_feature_{patient_key}"
cached = cache_get(cache_key)
if cached is not None:
    return cached
result = compute_expensive(patient_key)
cache_set(cache_key, result, ttl_key="my_feature")  # TTL _PERF_CACHE_TTL'den
return result
```

### 4. safe_html() XSS guard
```python
sh = safe_html
content = f"<div>Hasta: {sh(hasta_adi)}</div>"
```

### 5. permission_required + login_required
```python
@app.route("/api/yeni-endpoint", methods=["POST"])
@login_required
def api_yeni():
    if str(session.get("role") or "") != "doktor":
        return jsonify({"ok": False, "error": "Sadece doktor"}), 403
    ...
```

