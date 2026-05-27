"""YazKlinik XTTS-v2 dual-voice streaming TTS mikroservisi (port 9002).

XTTS-v2 voice cloning ile **2 ses** desteği:
  - "emel"  -> Edge TTS Emel referansli kadin sesi
  - "ahmet" -> Edge TTS Ahmet referansli erkek sesi

3 endpoint:
  POST /tts             - JSON {"text", "voice"="emel|ahmet"} - tum WAV doner
  POST /tts/stream      - JSON {"text", "voice"} - chunked WAV (sub-saniye TTFB)
  GET  /health          - servis durumu

RTX 5090 GPU'da ~200ms first chunk (streaming), tum WAV ~1200ms.
Internet bagimsiz, %100 lokal.
"""
from __future__ import annotations

import os
import sys
import atexit
import tempfile

_XTTS_LOCK_HANDLE = None


def _acquire_singleton_lock() -> None:
    """Prevent duplicate XTTS model loads on the same local port."""
    global _XTTS_LOCK_HANDLE
    port = (os.environ.get("YAZKLINIK_XTTS_SERVICE_PORT", "9002") or "9002").strip()
    lock_dir = os.path.join(tempfile.gettempdir(), "YazKlinik", "locks")
    os.makedirs(lock_dir, exist_ok=True)
    lock_path = os.path.join(lock_dir, f"xtts_{port}.lock")
    fh = open(lock_path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(
            f"[XTTS-SVC] Another XTTS instance is already running "
            f"(lock: {lock_path}); exiting.",
            flush=True,
        )
        try:
            fh.close()
        except Exception:
            pass
        sys.exit(0)
    try:
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()).encode("ascii", errors="ignore"))
        fh.flush()
    except Exception:
        pass
    _XTTS_LOCK_HANDLE = fh

    def _release_lock() -> None:
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            fh.close()
        except Exception:
            pass

    atexit.register(_release_lock)


_acquire_singleton_lock()

# FFmpeg shared DLL path (torchcodec audio IO icin gerekli, PyTorch 2.12+)
try:
    _here = os.path.dirname(os.path.abspath(__file__))
    _ffmpeg_bin = os.path.join(
        _here, "models", "ffmpeg", "extracted",
        "ffmpeg-n7.1-latest-win64-gpl-shared-7.1", "bin")
    if os.path.isdir(_ffmpeg_bin):
        os.environ["PATH"] = _ffmpeg_bin + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(_ffmpeg_bin)
        except (AttributeError, OSError):
            pass
except Exception:
    pass

# Torch'un kendi cuDNN DLL'ini onceliklendir (nvidia-cudnn-cu12 ile mismatch yasanmasin)
try:
    _venv_root = os.path.dirname(os.path.dirname(sys.executable))
    _torch_lib = os.path.join(_venv_root, "Lib", "site-packages", "torch", "lib")
    if os.path.isdir(_torch_lib):
        os.environ["PATH"] = _torch_lib + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(_torch_lib)
        except (AttributeError, OSError):
            pass
    _cublas = os.path.join(_venv_root, "Lib", "site-packages", "nvidia", "cublas", "bin")
    if os.path.isdir(_cublas):
        os.environ["PATH"] = _cublas + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(_cublas)
        except (AttributeError, OSError):
            pass
except Exception:
    pass

os.environ.setdefault("COQUI_TOS_AGREED", "1")

import io
import logging
import struct
import threading
import time
import wave

import numpy as np
from flask import Flask, jsonify, request, Response, stream_with_context


PORT = int(os.environ.get("YAZKLINIK_XTTS_SERVICE_PORT", "9002"))
DEVICE_PREF = os.environ.get("YAZKLINIK_XTTS_DEVICE", "auto").lower()
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "models", "xtts")

# Voice profile -> reference WAV path
VOICE_REFS = {
    "emel": os.path.join(MODELS_DIR, "emel_reference.wav"),
    "ahmet": os.path.join(MODELS_DIR, "ahmet_reference.wav"),
}
DEFAULT_VOICE = os.environ.get("YAZKLINIK_XTTS_DEFAULT_VOICE", "emel").lower()
if DEFAULT_VOICE not in VOICE_REFS:
    DEFAULT_VOICE = "emel"

SAMPLE_RATE = 24000  # XTTS-v2 native sample rate
STREAM_CHUNK_SIZE = int(os.environ.get("YAZKLINIK_XTTS_CHUNK_SIZE", "20"))

app = Flask(__name__)
_TTS = None
_MODEL = None  # underlying tts_model for streaming
_DEVICE = "cpu"
_LATENT_CACHE: dict[str, tuple] = {}  # voice -> (gpt_cond_latent, speaker_embedding)
_LOCK = threading.Lock()


def _load_model() -> None:
    global _TTS, _MODEL, _DEVICE
    import torch
    # Coqui TTS'in bazi surumleri transformers.pytorch_utils icindeki
    # isin_mps_friendly fonksiyonunu bekliyor. Transformers 5.x'te bu export
    # kalktigi icin XTTS servis import asamasinda dusuyordu.
    try:
        import transformers.pytorch_utils as _ptu  # type: ignore
        if not hasattr(_ptu, "isin_mps_friendly"):
            def _isin_mps_friendly(elements, test_elements):
                if hasattr(torch, "isin"):
                    return torch.isin(elements, test_elements)
                return (elements[..., None] == test_elements).any(-1)
            _ptu.isin_mps_friendly = _isin_mps_friendly  # type: ignore[attr-defined]
    except Exception:
        pass
    from TTS.api import TTS as CoquiTTS

    if DEVICE_PREF == "cpu":
        _DEVICE = "cpu"
    elif DEVICE_PREF == "cuda" and torch.cuda.is_available():
        _DEVICE = "cuda"
    else:
        _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

    t0 = time.time()
    print(f"[XTTS-SVC] Loading XTTS-v2 on {_DEVICE}...", flush=True)
    _TTS = CoquiTTS("tts_models/multilingual/multi-dataset/xtts_v2",
                    progress_bar=False).to(_DEVICE)
    _MODEL = _TTS.synthesizer.tts_model
    print(f"[XTTS-SVC] Model loaded in {(time.time()-t0)*1000:.0f} ms "
          f"(device={_DEVICE})", flush=True)

    # Pre-compute conditioning latents for both voices (1 kez yapilir, sonra hizli)
    for voice_name, ref_path in VOICE_REFS.items():
        if not os.path.isfile(ref_path):
            print(f"[XTTS-SVC] HATA: {voice_name} reference yok: {ref_path}", flush=True)
            continue
        try:
            tc = time.time()
            gpt_cond_latent, speaker_embedding = _MODEL.get_conditioning_latents(
                audio_path=ref_path,
                gpt_cond_len=_MODEL.config.gpt_cond_len,
                gpt_cond_chunk_len=_MODEL.config.gpt_cond_chunk_len,
                max_ref_length=_MODEL.config.max_ref_len,
                sound_norm_refs=_MODEL.config.sound_norm_refs,
            )
            _LATENT_CACHE[voice_name] = (gpt_cond_latent, speaker_embedding)
            print(f"[XTTS-SVC] Voice '{voice_name}' conditioning cached "
                  f"in {(time.time()-tc)*1000:.0f} ms", flush=True)
        except Exception as exc:
            print(f"[XTTS-SVC] HATA conditioning '{voice_name}': "
                  f"{type(exc).__name__}: {exc}", flush=True)


def _wav_header_streaming(sample_rate: int = SAMPLE_RATE) -> bytes:
    """WAV header with 'infinite' length so browser keeps reading the stream."""
    h = b"RIFF"
    h += struct.pack("<I", 0xFFFFFFFF)  # chunk size (max u32 = streaming)
    h += b"WAVE"
    h += b"fmt "
    h += struct.pack("<I", 16)          # fmt sub-chunk size
    h += struct.pack("<H", 1)           # PCM
    h += struct.pack("<H", 1)           # mono
    h += struct.pack("<I", sample_rate)
    h += struct.pack("<I", sample_rate * 2)  # byte rate (16-bit mono)
    h += struct.pack("<H", 2)           # block align
    h += struct.pack("<H", 16)          # bits per sample
    h += b"data"
    h += struct.pack("<I", 0xFFFFFFFF)  # data size = max (streaming)
    return h


def _resolve_voice(name: str | None) -> str:
    n = (name or "").strip().lower()
    if n in VOICE_REFS and n in _LATENT_CACHE:
        return n
    return DEFAULT_VOICE if DEFAULT_VOICE in _LATENT_CACHE else next(iter(_LATENT_CACHE))


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": _TTS is not None,
        "model": "xtts_v2",
        "device": _DEVICE,
        "voices": list(_LATENT_CACHE.keys()),
        "default_voice": DEFAULT_VOICE,
        "port": PORT,
    })


@app.route("/tts", methods=["POST"])
def tts_full():
    """Full WAV response (legacy mod). Streaming icin /tts/stream kullan."""
    if _TTS is None:
        return jsonify({"ok": False, "error": "model yuklenmedi"}), 503
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "metin yok"}), 400
    if len(text) > 2200:
        text = text[:2200].rsplit(" ", 1)[0]
    voice = _resolve_voice(data.get("voice"))

    t0 = time.time()
    try:
        with _LOCK:
            wav = _TTS.tts(text=text,
                           speaker_wav=VOICE_REFS[voice],
                           language="tr")
    except Exception as exc:
        print(f"[XTTS-SVC] tts HATA: {type(exc).__name__}: {exc}", flush=True)
        return jsonify({"ok": False, "error": str(exc)}), 500

    wav_arr = np.array(wav, dtype=np.float32)
    wav_int16 = (np.clip(wav_arr, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(wav_int16.tobytes())
    audio = buf.getvalue()

    elapsed_ms = (time.time() - t0) * 1000
    audio_sec = len(wav_int16) / SAMPLE_RATE
    rtf = elapsed_ms / (audio_sec * 1000) if audio_sec > 0 else 0
    print(f"[XTTS-SVC] FULL voice={voice} {elapsed_ms:.0f}ms "
          f"text-len={len(text)} audio={audio_sec:.2f}s rtf={rtf:.3f}", flush=True)

    return Response(audio, mimetype="audio/wav", headers={
        "Cache-Control": "no-store",
        "Content-Length": str(len(audio)),
    })


@app.route("/tts/stream", methods=["POST"])
def tts_stream():
    """Chunked WAV streaming - browser ilk chunk gelir gelmez calmaya baslar.

    XTTS-v2'nin gercek streaming API'sini (inference_stream) kullanir.
    Conditioning latents cache'lendigi icin first chunk ~200-400ms.
    """
    if _MODEL is None:
        return jsonify({"ok": False, "error": "model yuklenmedi"}), 503
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "metin yok"}), 400
    if len(text) > 2200:
        text = text[:2200].rsplit(" ", 1)[0]
    voice = _resolve_voice(data.get("voice"))
    gpt_cond_latent, speaker_embedding = _LATENT_CACHE[voice]

    def _generate():
        yield _wav_header_streaming(SAMPLE_RATE)
        t0 = time.time()
        first_chunk_at = None
        total_samples = 0
        try:
            with _LOCK:
                stream = _MODEL.inference_stream(
                    text=text,
                    language="tr",
                    gpt_cond_latent=gpt_cond_latent,
                    speaker_embedding=speaker_embedding,
                    stream_chunk_size=STREAM_CHUNK_SIZE,
                    enable_text_splitting=True,
                )
                for chunk in stream:
                    # chunk: torch tensor (samples,) float32 in [-1, 1]
                    arr = chunk.cpu().numpy().astype(np.float32)
                    arr_i16 = (np.clip(arr, -1.0, 1.0) * 32767).astype(np.int16)
                    total_samples += len(arr_i16)
                    if first_chunk_at is None:
                        first_chunk_at = (time.time() - t0) * 1000
                    yield arr_i16.tobytes()
        except GeneratorExit:
            return
        except Exception as exc:
            print(f"[XTTS-SVC] STREAM HATA: {type(exc).__name__}: {exc}", flush=True)
            return
        total_ms = (time.time() - t0) * 1000
        audio_sec = total_samples / SAMPLE_RATE
        rtf = total_ms / (audio_sec * 1000) if audio_sec > 0 else 0
        print(f"[XTTS-SVC] STREAM voice={voice} TTFB={first_chunk_at:.0f}ms "
              f"total={total_ms:.0f}ms audio={audio_sec:.2f}s rtf={rtf:.3f} "
              f"text-len={len(text)}", flush=True)

    return Response(stream_with_context(_generate()), mimetype="audio/wav",
                    headers={
                        "Cache-Control": "no-store",
                        "X-Accel-Buffering": "no",  # nginx buffer off
                    })


if __name__ == "__main__":
    _load_model()
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(f"[XTTS-SVC] Listening on http://127.0.0.1:{PORT}/tts (full) "
          f"and /tts/stream", flush=True)
    app.run(host="127.0.0.1", port=PORT, threaded=True, use_reloader=False)
