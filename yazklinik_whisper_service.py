"""YazKlinik Whisper mikroservisi â€” Whisper-ASR-Webservice uyumlu HTTP API.

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
import re

from flask import Flask, request, jsonify, Response


PORT = int(os.environ.get("YAZKLINIK_WHISPER_SERVICE_PORT", "9000"))
MODEL_NAME = os.environ.get("YAZKLINIK_WHISPER_MODEL", "small")
DEVICE = os.environ.get("YAZKLINIK_WHISPER_DEVICE", "cpu")
COMPUTE = os.environ.get("YAZKLINIK_WHISPER_COMPUTE_TYPE", "int8")
PROMPT_PROFILE = (
    os.environ.get("YAZKLINIK_WHISPER_PROMPT_PROFILE", "balanced")
    or "balanced"
).strip().lower()

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


def _prompt_for(mode: str = "strict") -> str | None:
    profile = PROMPT_PROFILE
    if profile in {"0", "off", "none", "false", "no"}:
        return None
    if mode == "relaxed":
        return (
            "Turkce konusma transkribi. Sadece duyulan kelimeleri yaz. "
            "Sessizlik ve arka plan sesini metne cevirme."
        )
    if profile in {"minimal", "lite", "safe"}:
        return (
            "Turkce klinik konusma. Sadece duyulan kelimeleri yaz. "
            "Duymadigin kisimlari uydurma."
        )
    return (
        "Turkce klinik konusma. Sadece duyulan kelimeleri yaz. "
        "Jinekoloji, obstetrik, gebelik, ultrason, recete, randevu."
    )


def _fold_tr_ascii(text: str) -> str:
    value = str(text or "").lower()
    pairs = (
        ("Ä±", "i"), ("Ä°", "i"), ("ÄŸ", "g"), ("Ã¼", "u"), ("ÅŸ", "s"),
        ("Ã¶", "o"), ("Ã§", "c"),
    )
    for src, dst in pairs:
        value = value.replace(src, dst)
    value = re.sub(r"[^a-z0-9\s]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _looks_stt_hallucinated(text: str) -> tuple[bool, str]:
    folded = _fold_tr_ascii(text)
    if not folded:
        return True, "empty"
    known = (
        "altyazi",
        "subtitle",
        "thanks for watching",
        "subscribe",
        "youtube",
        "siz jinekoloji bolumu icin",
        "sizi jinekoloji bolumu icin",
        "cinekoloji bolumu icin",
        "size daha once jinekoloji bolumu icin",
        "kinekoloji kelimesi",
    )
    for token in known:
        if token in folded:
            return True, f"known:{token}"
    words = [w for w in folded.split(" ") if w]
    if len(words) >= 3:
        counts = {}
        for w in words:
            counts[w] = counts.get(w, 0) + 1
        top_word = max(counts, key=counts.get)
        top_n = counts.get(top_word, 0)
        if top_n >= 3 and (top_n / float(len(words))) >= 0.60:
            return True, f"repeat:{top_word}x{top_n}"
    return False, "ok"


def _segment_quality_metrics(segments) -> tuple[float, float]:
    min_avg_logprob = 0.0
    max_no_speech = 0.0
    has_values = False
    for seg in (segments or []):
        try:
            avg = float(getattr(seg, "avg_logprob", 0.0) or 0.0)
            nos = float(getattr(seg, "no_speech_prob", 0.0) or 0.0)
            if not has_values:
                min_avg_logprob = avg
                max_no_speech = nos
                has_values = True
            else:
                min_avg_logprob = min(min_avg_logprob, avg)
                max_no_speech = max(max_no_speech, nos)
        except Exception:
            continue
    return min_avg_logprob, max_no_speech


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
    mean_db = None
    max_db = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            f.save(tf.name)
            tmp_path = tf.name
        # === D700 2026-05-26 GECICI MIC-DEBUG: gelen sesin seviyesini olc + kaydet ===
        # (tani amacli; sessiz=cihaz sorunu, kisik=sunucuda gain eklenebilir. Tani bitince kaldirilacak.)
        try:
            import subprocess as _sp, shutil as _sh, re as _re
            _dbg_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "temp", "mic_debug")
            os.makedirs(_dbg_dir, exist_ok=True)
            _dbg_path = os.path.join(_dbg_dir, f"mic_{int(time.time()*1000)}{suffix}")
            try:
                _sh.copy2(tmp_path, _dbg_path)
            except Exception:
                _dbg_path = "?"
            _vd = _sp.run(
                ["ffmpeg", "-hide_banner", "-i", tmp_path,
                 "-af", "volumedetect", "-f", "null", "-"],
                capture_output=True, text=True, timeout=20)
            _err = _vd.stderr or ""
            _mv = _re.search(r"mean_volume:\s*(-?[\d.]+) dB", _err)
            _pv = _re.search(r"max_volume:\s*(-?[\d.]+) dB", _err)
            try:
                mean_db = float(_mv.group(1)) if _mv else None
            except Exception:
                mean_db = None
            try:
                max_db = float(_pv.group(1)) if _pv else None
            except Exception:
                max_db = None
            print(
                f"[WHISPER-SVC][MIC-DEBUG] bytes={os.path.getsize(tmp_path)} "
                f"mean_volume={_mv.group(1) if _mv else '?'}dB "
                f"max_volume={_pv.group(1) if _pv else '?'}dB "
                f"saved={os.path.basename(str(_dbg_path))}", flush=True)
        except Exception as _dex:
            print(f"[WHISPER-SVC][MIC-DEBUG] err {_dex!r}", flush=True)
        # === /MIC-DEBUG ===
        with _LOCK:
            segments, info = _MODEL.transcribe(
                tmp_path,
                language=language,
                beam_size=5,
                best_of=5,
                temperature=0.0,
                vad_filter=True,
                vad_parameters={
                    # D700 v2: daha sÄ±kÄ± VAD - sessiz audio'da Whisper hiÃ§
                    # transkript yapmasÄ±n ("Verabal", "Nada Alex" tipi
                    # halÃ¼sinasyonlar gerÃ§ek sesten deÄŸil sessizden geliyordu)
                    "min_silence_duration_ms": 700,  # 500 -> 700 sÄ±kÄ±
                    "speech_pad_ms": 300,            # 400 -> 300 az
                    "threshold": 0.5,                # 0.4 -> 0.5 sÄ±kÄ±
                    "min_speech_duration_ms": 400,   # 250 -> 400 sÄ±kÄ±
                },
                condition_on_previous_text=False,
                # D700 HALUSINASYON ENGELLEME (v2 - cok daha agresif):
                # Whisper turbo gurultude "Verabal", "Neymar", "Nada Alex"
                # gibi rastgele kelimeler uydururdu. Threshold'lari sÄ±kÄ±:
                no_speech_threshold=0.7,  # 0.5 -> 0.7 cok sikica reject
                log_prob_threshold=-0.5,  # -0.7 -> -0.5 dusuk confidence reject
                compression_ratio_threshold=1.8,  # 2.2 -> 1.8 daha sÄ±kÄ±
                # D700: initial_prompt SADECE konuya ait kelimeler (instruction icermez).
                # OB/GYN + Alex + tibbi terimler genis liste - Whisper bu kelimeleri
                # tani ve dogru transkript et. "Opsetrik"/"preeklemsin" tipi yanlislar
                # bu prompt ile minimize olur.
                initial_prompt=_prompt_for("strict"),
            )
            segments = list(segments or [])
            text = " ".join(
                (getattr(s, "text", "") or "").strip()
                for s in segments).strip()
            min_avg_logprob, max_no_speech = _segment_quality_metrics(segments)
            decode_mode = "strict"
            if not text:
                try:
                    segments_relaxed, info_relaxed = _MODEL.transcribe(
                        tmp_path,
                        language=language,
                        beam_size=3,
                        best_of=3,
                        temperature=0.2,
                        vad_filter=True,
                        vad_parameters={
                            "min_silence_duration_ms": 420,
                            "speech_pad_ms": 350,
                            "threshold": 0.35,
                            "min_speech_duration_ms": 220,
                        },
                        condition_on_previous_text=False,
                        no_speech_threshold=0.55,
                        log_prob_threshold=-0.9,
                        compression_ratio_threshold=2.2,
                        initial_prompt=_prompt_for("relaxed"),
                    )
                    segments_relaxed = list(segments_relaxed or [])
                    relaxed_text = " ".join(
                        (getattr(s, "text", "") or "").strip()
                        for s in segments_relaxed
                    ).strip()
                    if relaxed_text:
                        text = relaxed_text
                        info = info_relaxed
                        decode_mode = "relaxed"
                        min_avg_logprob, max_no_speech = _segment_quality_metrics(
                            segments_relaxed)
                except Exception as relaxed_ex:
                    print(f"[WHISPER-SVC] relaxed retry hata: {relaxed_ex!r}", flush=True)
        hallucinated, hall_reason = _looks_stt_hallucinated(text)
        if text and hallucinated:
            print(f"[WHISPER-SVC] hallucination gate: {hall_reason}", flush=True)
            text = ""
        if text and max_no_speech >= 0.80 and min_avg_logprob <= -0.90:
            print(
                "[WHISPER-SVC] quality gate: "
                f"max_no_speech={max_no_speech:.2f} "
                f"min_avg_logprob={min_avg_logprob:.2f}",
                flush=True,
            )
            text = ""
        if text and mean_db is not None and max_db is not None:
            if mean_db <= -44.0 and max_db <= -22.0:
                print(
                    f"[WHISPER-SVC] low-volume gate: mean={mean_db:.1f} max={max_db:.1f}",
                    flush=True,
                )
                text = ""
        dt = time.time() - t0
        print(
            f"[WHISPER-SVC] {dt:.1f}s mode={decode_mode} lang={info.language} "
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

