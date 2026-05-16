"""Run a YazKlinik service without opening an extra console window.

Called by D300_BASLAT.bat through pythonw.exe:
    pythonw.exe D300_SERVICE_RUNNER.py service.py out.log err.log
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _load_config_env() -> None:
    path = ROOT / "config.env"
    if not path.exists():
        return
    try:
        for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip()
    except Exception:
        pass


def main() -> int:
    if len(sys.argv) < 4:
        return 2
    script = Path(sys.argv[1])
    if not script.is_absolute():
        script = ROOT / script
    out_log = Path(sys.argv[2])
    err_log = Path(sys.argv[3])
    out_log.parent.mkdir(parents=True, exist_ok=True)
    err_log.parent.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)
    _load_config_env()
    with out_log.open("a", encoding="utf-8", buffering=1) as out, err_log.open(
        "a", encoding="utf-8", buffering=1
    ) as err:
        sys.stdout = out
        sys.stderr = err
        print(f"[D300-RUNNER] start {script}", flush=True)
        old_argv = sys.argv[:]
        try:
            sys.argv = [str(script)] + old_argv[4:]
            runpy.run_path(str(script), run_name="__main__")
        finally:
            sys.argv = old_argv
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
