"""YazKlinik Whisper mikroservisi — Whisper-ASR-Webservice uyumlu HTTP API.

yazklinik_web.py icindeki '_ai_phone_transcribe_audio_bytes' fonksiyonunun
HTTP fallback yolunu kullanir:
    POST http://localhost:9000/asr?output=text
    Form: audio_file (multipart), language (form/query)
    Response: plain text transcription (output=text) veya JSON (output=json)

Bu service yazklinik_web.py'den BAGIMSIZ bir Python process'tir.
Werkzeug threading + faster-whisper CTranslate2 deadlock'undan kacinir.

Calistirma:
    python yazklinik_whisper_service.py
    veya START_WHISPER_SERVICE.bat
"""
from __future__ import annotations

import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

try:
    import imageio_ffmpeg as _iio_ffmpeg
    _ff_exe = _iio_ffmpeg.get_ffmpeg_exe()
    _ff_dir = os.path.dirname(_ff_exe)
    _ff_dst = os.path.join(_ff_dir, "ffmpeg.exe")
    if not os.path.exists(_ff_dst):
        import shutil as _sh
        try:
            _sh.copy2(_ff_exe, _ff_dst)
        except Exception:
            pass
    os.environ["PATH"] = _ff_dir + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

import sys

# CUDA DLL path injection (cublas + cudnn). nvidia-cublas-cu12 / nvidia-cudnn-cu12 pip
# paketleri DLL'lerini venv\Lib\site-packages\nvidia\<lib>\bin altina koyar; Windows
# default PATH burayi bilmedigi icin faster-whisper CUDA transcribe sirasinda patlar.
try:
    _venv_root = os.path.dirname(os.path.dirname(sys.executable))
    _nvidia_root = os.path.join(_venv_root, "Lib", "site-packages", "nvidia")
    if os.path.isdir(_nvidia_root):
        for _sub in ("cublas", "cudnn"):
            _bindir = os.path.join(_nvidia_root, _sub, "bin")
            if os.path.isdir(_bindir):
                os.environ["PATH"] = _bindir + os.pathsep + os.environ.get("PATH", "")
                try:
                    os.add_dll_directory(_bindir)
                except (AttributeError, OSError):
                    pass
except Exception:
    pass

import tempfile
import threading
import time

from flask import Flask, request, jsonify, Response


PORT = int(os.environ.get("YAZKLINIK_WHISPER_SERVICE_PORT", "9000"))
MODEL_NAME = os.environ.get("YAZKLINIK_WHISPER_MODEL", "small")
DEVICE = os.environ.get("YAZKLINIK_WHISPER_DEVICE", "cpu")
COMPUTE = os.environ.get("YAZKLINIK_WHISPER_COMPUTE_TYPE", "int8")

app = Flask(__name__)
_MODEL = None
_LOCK = threading.Lock()


def _load_model() -> None:
    global _MODEL
    from faster_whisper import WhisperModel
    t0 = time.time()
    print(
        f"[WHISPER-SVC] Loading model={MODEL_NAME} device={DEVICE} "
        f"compute={COMPUTE}...",
        flush=True)
    _MODEL = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE)
    print(f"[WHISPER-SVC] Model loaded in {time.time()-t0:.1f}s", flush=True)


@app.route("/asr", methods=["POST"])
def asr():
    if _MODEL is None:
        return ("model henuz hazir degil", 503)
    f = request.files.get("audio_file")
    if f is None:
        return ("audio_file yok", 400)
    output = (request.args.get("output") or "text").lower()
    language = (
        request.form.get("language")
        or request.args.get("language")
        or "tr").strip() or "tr"
    suffix = os.path.splitext(f.filename or "audio.webm")[1] or ".webm"
    tmp_path = None
    t0 = time.time()
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            f.save(tf.name)
            tmp_path = tf.name
        with _LOCK:
            segments, info = _MODEL.transcribe(
                tmp_path,
                language=language,
                beam_size=5,
                best_of=5,
                temperature=0.0,
                vad_filter=True,
                vad_parameters={
                    # D300 v2: daha sıkı VAD - sessiz audio'da Whisper hiç
                    # transkript yapmasın ("Verabal", "Nada Alex" tipi
                    # halüsinasyonlar gerçek sesten değil sessizden geliyordu)
                    "min_silence_duration_ms": 700,  # 500 -> 700 sıkı
                    "speech_pad_ms": 300,            # 400 -> 300 az
                    "threshold": 0.5,                # 0.4 -> 0.5 sıkı
                    "min_speech_duration_ms": 400,   # 250 -> 400 sıkı
                },
                condition_on_previous_text=False,
                # D300 HALUSINASYON ENGELLEME (v2 - cok daha agresif):
                # Whisper turbo gurultude "Verabal", "Neymar", "Nada Alex"
                # gibi rastgele kelimeler uydururdu. Threshold'lari sıkı:
                no_speech_threshold=0.7,  # 0.5 -> 0.7 cok sikica reject
                log_prob_threshold=-0.5,  # -0.7 -> -0.5 dusuk confidence reject
                compression_ratio_threshold=1.8,  # 2.2 -> 1.8 daha sıkı
                # D300: initial_prompt SADECE konuya ait kelimeler (instruction icermez).
                # OB/GYN + Alex + tibbi terimler genis liste - Whisper bu kelimeleri
                # tani ve dogru transkript et. "Opsetrik"/"preeklemsin" tipi yanlislar
                # bu prompt ile minimize olur.
                initial_prompt=(
                    "Alex, Op. Dr. Hakan Yaz, doktor, hasta, gebelik, randevu, "
                    "recete, ilac, USG, ultrason, doppler, kardiyotokografi, "
                    "NT, BPD, AC, EFW, FL, HC, OFD, CRL, NF, AFI, "
                    "obstetrik, jinekoloji, gestasyonel, gebelik haftasi, "
                    "preeklampsi, eklampsi, plasenta, amnion, oligohidramnios, "
                    "polihidramnios, makrozomi, intrauterin, fetal, anomali, "
                    "tarama, smear, kolposkopi, biyopsi, histeroskopi, "
                    "laparoskopi, muayene, tahlil, kan, hormon, "
                    "TSH, FSH, LH, AMH, HCG, prolaktin, ostradiol, progesteron, "
                    "tiroid, diyabet, hipertansiyon, anemi, "
                    "infertilite, IVF, ICSI, tup bebek, inseminasyon, "
                    "ovulasyon, foliksul, embriyo, transfer, "
                    "dogum, sezeryan, normal dogum, indüksiyon, epidural, "
                    "lohusa, emzirme, postpartum, "
                    "polikistik over, endometriozis, miyom, kist, vajinit, "
                    "vulvavajinit, servisit, salpenjit, "
                    "menstruasyon, adet, kanama, lekelenme, agri, kasinti, "
                    "yumurtalik, rahim, serviks, vajina, tuba, over, uterus, "
                    "Pazartesi, Sali, Carsamba, Persembe, Cuma, Cumartesi, Pazar, "
                    "yarin, bugun, dun, oncegun, gelecek hafta, gecen hafta, "
                    "saat, dakika, hafta, ay, yil, gun. "
                    "PubMed, arastir, ozetle, bilgi bul, oku, hatirla, ogren."),
            )
            text = " ".join(
                (getattr(s, "text", "") or "").strip()
                for s in segments).strip()
        dt = time.time() - t0
        print(
            f"[WHISPER-SVC] {dt:.1f}s lang={info.language} "
            f"dur={info.duration:.1f}s text={text[:80]!r}",
            flush=True)
        if output in {"json", "verbose_json"}:
            return jsonify({
                "text": text,
                "language": info.language,
                "duration": info.duration,
            })
        return Response(text, mimetype="text/plain; charset=utf-8")
    except Exception as ex:
        print(f"[WHISPER-SVC] HATA: {ex!r}", flush=True)
        return (f"transcribe hata: {ex}", 500)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


@app.route("/health")
def health():
    return jsonify({
        "ok": _MODEL is not None,
        "model": MODEL_NAME,
        "device": DEVICE,
        "compute": COMPUTE,
        "port": PORT,
    })


def main() -> None:
    _load_model()
    print(
        f"[WHISPER-SVC] Listening on http://127.0.0.1:{PORT}/asr",
        flush=True)
    app.run(host="127.0.0.1", port=PORT, threaded=False)


if __name__ == "__main__":
    main()
