"""YazKlinik Whisper transcribe worker (subprocess izolasyon).

Werkzeug threading + faster-whisper CTranslate2 backend deadlock'undan
kacinmak icin bagimsiz Python process olarak calistirilir.

Args:
    --audio  <path>     Ses dosyasi (wav/webm/mp3/m4a/ogg)
    --lang   <code>     'tr' (default)
    --model  <name>     'small' (default)
    --device <dev>      'cpu' (default)
    --compute <type>    'int8' (default)
    --vad    0|1        VAD on/off (default 1)

Stdout:
    {"ok":true,"text":"...","lang":"tr","duration":3.5}
    {"ok":false,"error":"..."}
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> int:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--lang", default="tr")
    parser.add_argument("--model", default="small")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute", default="int8")
    parser.add_argument("--vad", default="1")
    args = parser.parse_args()

    try:
        from faster_whisper import WhisperModel

        model = WhisperModel(
            args.model, device=args.device, compute_type=args.compute)
        kwargs = {
            "language": (args.lang or "tr").strip() or "tr",
            "beam_size": 1,
            "condition_on_previous_text": False,
            "initial_prompt": (
                "Turkce doktor komutu. Arka plan muzik ve ortam "
                "seslerini yok say."),
        }
        if str(args.vad or "1").strip() not in {"0", "false", "no", "off"}:
            kwargs["vad_filter"] = True
            kwargs["vad_parameters"] = {
                "min_silence_duration_ms": 250,
                "speech_pad_ms": 120,
            }
        else:
            kwargs["vad_filter"] = False

        segments, info = model.transcribe(args.audio, **kwargs)
        text = " ".join(
            (getattr(seg, "text", "") or "").strip()
            for seg in segments).strip()
        sys.stdout.write(json.dumps({
            "ok": True,
            "text": text,
            "lang": getattr(info, "language", args.lang),
            "lang_prob": float(getattr(info, "language_probability", 0.0) or 0.0),
            "duration": float(getattr(info, "duration", 0.0) or 0.0),
        }))
        sys.stdout.flush()
        return 0
    except Exception as ex:
        sys.stdout.write(json.dumps({"ok": False, "error": repr(ex)}))
        sys.stdout.flush()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
