# CODEX_API_ENDPOINTS.md - Flask Route Listesi

> 470+ route var. Bu dosya **kullanici-yuzlu** ve **API** route'larini listeler.

## Login / Yetki

| Route | Method | Aciklama |
|---|---|---|
| `/giris` | GET, POST | Login sayfasi |
| `/cikis` | GET | Logout |
| `/sifre-degistir` | GET, POST | Sifre degistir |

## Hasta Yonetimi (UI)

| Route | Method | Aciklama |
|---|---|---|
| `/` | GET | Dashboard (giris sonrasi) |
| `/hastalar` | GET | Hasta listesi (lazy GA chip + autocomplete) |
| `/yeni-hasta` | GET, POST | Yeni hasta kayit |
| `/hasta/<key>` | GET | Hasta dosyasi anasayfa |
| `/hasta/<key>/sil` | POST | Hasta sil (sadece doktor) |
| `/arsivlenmis-hastalar` | GET | Silinen hastalari geri al |
| `/hasta-birlestir` | GET, POST | **D128 SUPER** 2 hasta merge |
| `/hasta/<key>/ozet-rapor` | GET | A4 ozet rapor |
| `/hasta/<key>/gelis/<visit_key>/...` | * | Gelis detayi (PDF/JPG/USG) |

## Klinik Modules (D128 SUPER)

| Route | Method | Aciklama |
|---|---|---|
| `/akilli-dialog` | GET | Alex AI chat (wake word "alex") |
| `/sessiz-alex` | GET | Klavye ile sessiz Alex dialog |
| `/ses-ve-alex` | GET | Ses ve Alex merkezi |
| `/alex-baslat` | GET | Alex tek-tikla baslat |
| `/tedavi-planla` | GET, POST | **Tedavi Planlayici** (autocomplete + DDI) |
| `/tedavi-planla/recete-cikti` | POST | A5 profesyonel recete (QR + DDI + RX no) |
| `/obgyn-rehber` | GET | OB/GYN textbook (11 kategori) |
| `/ilac-piyasa` | GET | Turkiye ilac marka DB |
| `/diyet-rehberi` | GET, POST | 8 senaryo diyet |
| `/gebelik-plani` | GET, POST | Hastaya ozel 40-haftalik plan |
| `/riskli-gebelik` | GET, POST | DM/HT/tiroid/APS/preterm |
| `/gebelik-komplikasyon` | GET, POST | HG/abortus/ektopik/PPH/HELLP |
| `/ivf-konsult` | GET, POST | IVF protokol |
| `/ovulasyon-induksiyon` | GET, POST | OI cycle |
| `/anormal-uterin-kanama` | GET, POST | AUB FIGO PALM-COEIN |
| `/endometrial-hiperplazi` | GET, POST | EH WHO 2014 |
| `/pelvik-enfeksiyon` | GET, POST | PID/vajinit/BV/klamidya |
| `/ilac-guvenlik` | GET, POST | Gebelikte ilac kategori + DDI |

## Sistem (D200)

| Route | Method | Aciklama |
|---|---|---|
| `/sistem-ayarlari` | GET, POST | **D200** NAS/DB/port edit |
| `/yk-ayarlar` | GET, POST | (alias) |
| `/sistem-durumu` | GET | UI sistem health |
| `/api/sistem-durumu` | GET | JSON sistem health |
| `/menu-ara` | GET | Menu arama |
| `/ayarlar` | GET | Genel ayar |
| `/ayarlar/dosya-yerleri` | GET, POST | Orthanc/DICOM URL |

## Hasta API (REST)

| Route | Method | Aciklama |
|---|---|---|
| `/api/hasta/<key>/arsivle` | POST | Hasta arsivle |
| `/api/hasta/<key>/geri-al` | POST | Arsivden geri al |
| `/api/hasta/<key>/diyet-listele` | GET | Diyet kayitlari |
| `/api/hasta/<key>/diyet-kaydet` | POST | Diyet kaydet |
| `/api/hasta/<key>/sesli-recete/parse` | POST | Sesli recete parse |
| `/api/hasta/<key>/konusarak-not` | POST | Konusarak not ekle |
| `/api/hasta/<key>/veri-onerisi` | POST | Veri cakismasi cozum |
| `/api/hasta/<key>/gelis/<visit>/klasor-ac` | POST | Klasoru explorer'da ac |

## Tedavi/Recete API (D128 SUPER)

| Route | Method | Aciklama |
|---|---|---|
| `/api/tedavi-hasta-ara?q=...` | GET | Hasta autocomplete (DB'den) |
| `/api/tedavi-hasta-detay?key=...` | GET | Hasta detayi (SAT PDF/demo'dan) |
| `/api/hasta-ga-batch?keys=k1,k2` | GET | Batch GA hesap (chip icin) |
| `/api/hasta-birlestir-onizleme` | POST | Merge dry-run (kac satir tasinacak) |
| `/api/hasta-birlestir` | POST | Gercek merge |
| `/api/recete-katalog-ara` | GET | Ilac/tani autocomplete |
| `/api/recete-cikti-ayar` | POST | Print ayar kaydet |

## YZ / Alex API

| Route | Method | Aciklama |
|---|---|---|
| `/api/alex-runtime/start` | POST | Alex backend ASR aktif |
| `/api/alex-runtime/stop` | POST | Alex kapat |
| `/api/alex-runtime/status` | GET | Durum |
| `/api/phone/live-transcribe` | POST | Whisper transcribe |
| `/api/phone/live-native-record` | POST | Native mikrofon kayit |
| `/ses-profilleri` | GET, POST | Alex/TTS ses secimi |
| `/mikrofon-tani` | GET | Mikrofon tani ve test |
| `/api/yz/durum` | GET | YZ provider durum |

## DICOM / USG

| Route | Method | Aciklama |
|---|---|---|
| `/dicom` | GET | DICOM viewer |
| `/api/hasta/<key>/dicom` | GET | Hasta DICOM listele |
| `/api/hasta/<key>/viewpoint-pro` | GET | ViewPoint Pro entegre |
| `/api/hasta/<key>/dicom/worklist-update` | POST | Worklist guncelle |

## Telefon / WhatsApp

| Route | Method | Aciklama |
|---|---|---|
| `/telefon-ara` | GET, POST | Telefon arama |
| `/api/phone/...` | * | Telefon API'lar |

## Yardimci

| Route | Method | Aciklama |
|---|---|---|
| `/api/feature-sync` | GET | Sidebar manifest JSON |
| `/api/yk-secret-version` | GET | API version |
| `/api/ozellik-senkron` | GET | Feature sync (alias) |
| `/api/ui/experience-mode` | GET, POST | Doctor/asistan mode |

## Onemli Notlar

- **Tum API'lar JSON donerler** (`Content-Type: application/json`)
- **Login gerekli** - tum route'lar `@login_required` decorator'lu (sadece `/giris` ve `/saglik` haric)
- **Doktor only** - bazi route'lar `if session.get("role") != "doktor": return 403`
- **CSRF** - genelde Flask session cookie ile, manuel POST'larda Cookie header lazim
- **Rate limit** - yok (lokal kullanim)

## Klinik Ajanlari (2026-05-16, Blueprint = `agents_bp`)

> Detayli handoff: [CODEX_HANDOFF_2026-05-16_AJANLAR.md](CODEX_HANDOFF_2026-05-16_AJANLAR.md)
> Wire dosyasi: `yazklinik_agents_routes.py` (yeni)
> Modul dosyalari: `yazklinik_<id>_agent.py` (10 adet)

| Route | Method | Aciklama |
|---|---|---|
| `/ajanlar` | GET | 10 ajan dashboard (HTML, kart grid + manifest dump) |
| `/api/agents` | GET | Manifest + modul import durumu |
| `/api/agents/telesekreter/run` | POST | Cagri triyaji - niyet/aciliyet/onerilen slot |
| `/api/agents/sesli_onay/run` | POST | "Evet/hayir/ertele" yaniti -> randevu kararı |
| `/api/agents/usg_rapor/run` | POST | BPD/HC/AC/FL -> Hadlock EFW + rapor TASLAGI |
| `/api/agents/geri_cagirma/run` | POST | Kontrol/asi/postop hatirlatma kuyrugu (KVKK) |
| `/api/agents/bk_sync_bekci/run` | POST | BulutKlinik OAuth/cookie saglik |
| `/api/agents/nas_yedek_izleyici/run` | POST | NAS yedek + disk doluluk (read-only) |
| `/api/agents/recete_hazirlayici/run` | POST | Gecmis + alerji ile recete TASLAGI |
| `/api/agents/gunluk_ozet/run` | POST | Gun sonu trafik + ciro + bekleyenler |
| `/api/agents/mojibake_bekci/run` | POST | Encoding bozuklugu (SADECE TESPIT, auto-fix YOK) |
| `/api/agents/pr_reviewer/run` | POST | Diff sablon kontrol (v68/DELETE/NAS unlink) |

**Standart cevap:** `{"ok": true, "agent": "<id>", "result": {...}}`
**Hata kodlari:** 401 auth_required · 400 bad_request · 500 agent_failure · 503 module_import_failed

## Yeni Route Ekleme Pattern

```python
@app.route("/api/yeni-endpoint", methods=["POST"])
@login_required
def api_yeni_endpoint():
    """D200: Yeni feature aciklamasi."""
    if str(session.get("role") or "") != "doktor":
        return jsonify({"ok": False, "error": "Sadece doktor"}), 403

    body = request.get_json(silent=True) or {}
    param = str(body.get("param") or "").strip()
    if not param:
        return jsonify({"ok": False, "error": "param gerekli"}), 400

    try:
        result = compute_something(param)
        return jsonify({"ok": True, "result": result})
    except Exception as ex:
        return jsonify({"ok": False, "error": str(ex)}), 500
```

Sonra `yazklinik_feature_sync.py`'a sidebar kayit eklenir:

```python
_r("/yeni-endpoint", "Yeni Endpoint", "Aciklama", "patient", "[NEW]",
   aliases=("yeni", "new endpoint")),
```

