"""Open a local folder requested by YazKlinik WebShell.

The web app emits yazklinik-open-folder://open?path=... links when a terminal
PC should open a visit/NAS folder locally. This helper keeps that behavior out
of the browser sandbox.
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.parse
from pathlib import Path


def _extract_path(raw_url: str) -> str:
    parsed = urllib.parse.urlparse(str(raw_url or ""))
    query = urllib.parse.parse_qs(parsed.query or "")
    value = ""
    for key in ("path", "folder", "dir"):
        if query.get(key):
            value = query[key][0]
            break
    if not value and parsed.path:
        value = urllib.parse.unquote(parsed.path.lstrip("/"))
    return urllib.parse.unquote(value or "").strip().strip('"')


def _open_path(path_text: str) -> int:
    if not path_text:
        return 2
    path = Path(path_text)
    if not path.exists():
        return 3
    if os.name == "nt":
        subprocess.Popen(["explorer", str(path)])
        return 0
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return 0
    subprocess.Popen(["xdg-open", str(path)])
    return 0


def main(argv: list[str]) -> int:
    raw = argv[1] if len(argv) > 1 else ""
    return _open_path(_extract_path(raw))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
