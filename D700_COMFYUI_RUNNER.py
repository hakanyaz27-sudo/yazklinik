"""Start local ComfyUI for YazKlinik D700."""
from __future__ import annotations

import os
import runpy
import shlex
import sys
from pathlib import Path
from urllib.parse import urlsplit


def _norm_args(raw: str) -> list[str]:
    args: list[str] = []
    for item in shlex.split(str(raw or "")):
        item = item.strip()
        if not item:
            continue
        if item == "--fp16":
            item = "--force-fp16"
        if item not in args:
            args.append(item)
    return args


def main() -> int:
    home = Path(
        os.environ.get("YAZKLINIK_COMFYUI_HOME", "").strip()
        or r"C:\YazKlinik_AI\ComfyUI"
    ).expanduser()
    main_py = home / "main.py"
    if not main_py.exists():
        print(f"ComfyUI main.py bulunamadi: {main_py}", flush=True)
        return 2
    url = os.environ.get("YAZKLINIK_COMFYUI_URL", "http://127.0.0.1:8188")
    try:
        port = int(urlsplit(url).port or 8188)
    except Exception:
        port = 8188
    gpu_args = _norm_args(
        os.environ.get("YAZKLINIK_COMFYUI_GPU_ARGS", "--highvram --force-fp16")
    )
    os.chdir(home)
    sys.path.insert(0, str(home))
    sys.argv = [
        str(main_py),
        "--listen",
        "0.0.0.0",
        "--port",
        str(port),
        "--enable-manager",
        *gpu_args,
    ]
    print("ComfyUI argv:", " ".join(sys.argv), flush=True)
    runpy.run_path(str(main_py), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

