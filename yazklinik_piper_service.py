"""YazKlinik Piper TTS mikroservisi - lokal Turkce TTS (port 9001).

Edge TTS yerine kullanilir (Edge TTS Microsoft Azure cloud'una giderken ~1400ms
latency yapiyor; Piper lokal ONNX, RTX 5090 PC'de ~67ms / 4s audio = RTF 0.018).

POST /tts JSON body: {"text": "..."}
Response: audio/wav (Piper native 22050Hz 16-bit mono PCM)

GET /health
Response: {"ok": bool, "model": "...", "cuda": bool, "port": 9001}

Calistirma:
    python yazklinik_piper_service.py
    veya START_PIPER_SERVICE.bat
"""
from __future__ import annotations

import os
import sys

# CUDA DLL path (onnxruntime CUDA provider icin - CPU'da da hizli zaten)
try:
    _venv_root = os.path.dirname(os.path.dirname(sys.executable))
    _nvidia = os.path.join(_venv_root, "Lib", "site-packages", "nvidia")
    if os.path.isdir(_nvidia):
        for _sub in ("cublas", "cudnn"):
            _bindir = os.path.join(_nvidia, _sub, "bin")
            if os.path.isdir(_bindir):
                os.environ["PATH"] = _bindir + os.pathsep + os.environ.get("PATH", "")
                try:
                    os.add_dll_directory(_bindir)
                except (AttributeError, OSError):
                    pass
except Exception:
    pass

import io
import logging
import threading
import time
import wave

from flask import Flask, jsonify, request, Response
from piper import PiperVoice


PORT = int(os.environ.get("YAZKLINIK_PIPER_SERVICE_PORT", "9001"))
MODEL = os.environ.get(
    "YAZKLINIK_PIPER_MODEL",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "models", "piper", "tr_TR-dfki-medium.onnx"))
USE_CUDA = os.environ.get("YAZKLINIK_PIPER_CUDA", "0") == "1"

app = Flask(__name__)
_VOICE: PiperVoice | None = None
_LOCK = threading.Lock()
_SAMPLE_RATE = 22050


def _load_model() -> None:
    global _VOICE, _SAMPLE_RATE
    t0 = time.time()
    print(f"[PIPER-SVC] Loading model={MODEL} cuda={USE_CUDA}...", flush=True)
    _VOICE = PiperVoice.load(MODEL, use_cuda=USE_CUDA)
    elapsed = (time.time() - t0) * 1000
    print(f"[PIPER-SVC] Model loaded in {elapsed:.0f} ms", flush=True)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": _VOICE is not None,
        "model": os.path.basename(MODEL),
        "cuda": USE_CUDA,
        "port": PORT,
    })


@app.route("/tts", methods=["POST"])
def tts():
    if _VOICE is None:
        return jsonify({"ok": False, "error": "model yuklenmedi"}), 503

    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "metin yok"}), 400

    if len(text) > 2400:
        text = text[:2400].rsplit(" ", 1)[0]

    t0 = time.time()
    try:
        with _LOCK:
            chunks = list(_VOICE.synthesize(text))
    except Exception as exc:
        print(f"[PIPER-SVC] synth HATA: {type(exc).__name__}: {exc}", flush=True)
        return jsonify({"ok": False, "error": str(exc)}), 500

    if not chunks:
        return jsonify({"ok": False, "error": "bos cikti"}), 500

    sr = chunks[0].sample_rate
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        for c in chunks:
            wf.writeframes(c.audio_int16_bytes)
    audio = buf.getvalue()
    elapsed_ms = (time.time() - t0) * 1000
    audio_sec = sum(len(c.audio_int16_bytes) for c in chunks) / (2 * sr)
    rtf = elapsed_ms / (audio_sec * 1000) if audio_sec > 0 else 0
    print(
        f"[PIPER-SVC] {elapsed_ms:.0f}ms text-len={len(text)} "
        f"audio={audio_sec:.2f}s rtf={rtf:.3f}", flush=True)
    return Response(audio, mimetype="audio/wav", headers={
        "Cache-Control": "no-store",
        "Content-Length": str(len(audio)),
    })


if __name__ == "__main__":
    _load_model()
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(f"[PIPER-SVC] Listening on http://127.0.0.1:{PORT}/tts", flush=True)
    app.run(host="127.0.0.1", port=PORT, threaded=True, use_reloader=False)
