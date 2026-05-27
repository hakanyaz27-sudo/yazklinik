#!/usr/bin/env python3
"""D700 hasta portali ayrim kaniti.

Bu kontrol hasta verisi silmez. Test icin kisa omurlu bir portal token'i
olusturur, hem ana uygulama hem ayri hasta portali uzerinden dener ve sonunda
token'i revoked_at ile iptal eder.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sqlite3
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
    install_opener,
    urlopen,
)


ROOT = Path(__file__).resolve().parent
CONFIG_ENV = ROOT / "config.env"
DEFAULT_DB = ROOT / "local_db" / "yazklinik_v68.sqlite3"
PATIENT_HOST = "hasta.yazhakan.com.tr"
MAIN_PUBLIC = "https://yazhakan.com.tr/"
PATIENT_PUBLIC = "https://hasta.yazhakan.com.tr/"
LOCAL_MAIN = "http://127.0.0.1:5052"
LOCAL_PATIENT = "http://127.0.0.1:5053"
TIMEOUT = 15


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


install_opener(build_opener(NoRedirect))


@dataclass
class CheckResult:
    label: str
    ok: bool
    detail: str = ""
    warn: bool = False


class Checker:
    def __init__(self) -> None:
        self.results: list[CheckResult] = []

    def ok(self, label: str, detail: str = "") -> None:
        self.results.append(CheckResult(label, True, detail))
        print(f"[OK]   {label}{' - ' + detail if detail else ''}")

    def warn(self, label: str, detail: str = "") -> None:
        self.results.append(CheckResult(label, True, detail, warn=True))
        print(f"[WARN] {label}{' - ' + detail if detail else ''}")

    def fail(self, label: str, detail: str = "") -> None:
        self.results.append(CheckResult(label, False, detail))
        print(f"[FAIL] {label}{' - ' + detail if detail else ''}")

    def expect(self, label: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.ok(label, detail)
        else:
            self.fail(label, detail)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)

    @property
    def warned(self) -> int:
        return sum(1 for r in self.results if r.warn)


def load_config_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not CONFIG_ENV.exists():
        return env
    for raw in CONFIG_ENV.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def env_value(config: dict[str, str], key: str, default: str = "") -> str:
    return os.environ.get(key) or config.get(key) or default


def http_request(
    url: str,
    *,
    host: str | None = None,
    timeout: int = TIMEOUT,
    no_verify: bool = True,
    attempts: int = 4,
) -> tuple[int, dict[str, str], str]:
    headers = {"User-Agent": "D700-PatientPortalSplitCheck/1.0"}
    if host:
        headers["Host"] = host
    context = None
    if url.lower().startswith("https://") and no_verify:
        context = ssl._create_unverified_context()  # noqa: SLF001
    last_error = ""
    for attempt in range(1, max(1, attempts) + 1):
        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=timeout, context=context) as resp:
                body = resp.read(200000).decode("utf-8", errors="replace")
                return int(resp.status), dict(resp.headers.items()), body
        except HTTPError as exc:
            body = exc.read(200000).decode("utf-8", errors="replace")
            return int(exc.code), dict(exc.headers.items()), body
        except URLError as exc:
            last_error = str(exc.reason)
        except TimeoutError as exc:
            last_error = str(exc)
        if attempt < attempts:
            time.sleep(2)
    raise RuntimeError(last_error or "baglanti hatasi")


def db_path(config: dict[str, str]) -> Path:
    raw = env_value(config, "YAZKLINIK_DB_PATH", str(DEFAULT_DB))
    return Path(raw)


def ensure_schema(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS patient_portal_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            patient_key TEXT NOT NULL,
            patient_name TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT,
            expires_at TEXT,
            revoked_at TEXT,
            last_access_at TEXT
        )
        """
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_patient_portal_token "
        "ON patient_portal_links(token)"
    )


def create_test_token(db_file: Path) -> str:
    token = secrets.token_hex(24)
    now = datetime.now()
    expires = now + timedelta(minutes=10)
    with sqlite3.connect(db_file, timeout=10) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=7000")
        ensure_schema(con)
        row = con.execute(
            """
            SELECT folder_key, display_name
            FROM patients
            WHERE COALESCE(archived_at, '') = ''
            ORDER BY rowid
            LIMIT 1
            """
        ).fetchone()
        if not row:
            raise RuntimeError("aktif hasta kaydi bulunamadi")
        con.execute(
            """
            INSERT INTO patient_portal_links(
                token, patient_key, patient_name, created_at, created_by, expires_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                token,
                row["folder_key"],
                row["display_name"] or row["folder_key"],
                now.isoformat(sep=" ", timespec="seconds"),
                "codex-split-check",
                expires.isoformat(sep=" ", timespec="seconds"),
            ),
        )
        con.commit()
    return token


def revoke_test_token(db_file: Path, token: str) -> None:
    if not token:
        return
    with sqlite3.connect(db_file, timeout=10) as con:
        con.execute(
            "UPDATE patient_portal_links SET revoked_at=? WHERE token=?",
            (datetime.now().isoformat(sep=" ", timespec="seconds"), token),
        )
        con.commit()


def cloudflared_config_path() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".cloudflared" / "config.yml"


def cloudflared_has_patient_ingress(config_path: Path) -> bool:
    if not config_path.exists():
        return False
    lines = config_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for idx, line in enumerate(lines):
        if "hostname:" in line and PATIENT_HOST in line:
            window = "\n".join(lines[idx : idx + 4])
            return "127.0.0.1:5053" in window
    return False


def require_status(
    c: Checker,
    label: str,
    url: str,
    expected: int | Iterable[int],
    *,
    host: str | None = None,
    contains: str | None = None,
    header_contains: tuple[str, str] | None = None,
    attempts: int = 4,
) -> tuple[int, dict[str, str], str]:
    try:
        status, headers, body = http_request(url, host=host, attempts=attempts)
    except Exception as exc:  # noqa: BLE001
        c.fail(label, f"baglanti hatasi: {exc}")
        return 0, {}, ""
    expected_set = {expected} if isinstance(expected, int) else set(expected)
    if status not in expected_set:
        c.fail(label, f"HTTP {status}, beklenen {sorted(expected_set)}")
        return status, headers, body
    if contains and contains not in body:
        c.fail(label, f"HTTP {status}, govdede beklenen metin yok: {contains}")
        return status, headers, body
    if header_contains:
        name, needle = header_contains
        value = headers.get(name, "")
        if needle.lower() not in value.lower():
            c.fail(label, f"{name}={value!r}, beklenen: {needle!r}")
            return status, headers, body
    c.ok(label, f"HTTP {status}")
    return status, headers, body


def main() -> int:
    parser = argparse.ArgumentParser(description="D700 hasta portali ayrim smoke testi")
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Cloudflare/public HTTPS kontrollerini atla.",
    )
    args = parser.parse_args()
    c = Checker()
    config = load_config_env()
    db_file = db_path(config)
    base_url = env_value(config, "YAZKLINIK_PATIENT_PORTAL_BASE_URL", PATIENT_PUBLIC.rstrip("/"))
    base_host = urlsplit(base_url if "://" in base_url else f"https://{base_url}").hostname or ""

    print("=== D700 Hasta Portal Ayrim Kontrolu ===")
    c.expect("config.env mevcut", CONFIG_ENV.exists(), str(CONFIG_ENV))
    c.expect("DB mevcut", db_file.exists(), str(db_file))
    c.expect(
        "hasta portali aktif",
        env_value(config, "YAZKLINIK_PATIENT_PORTAL_ENABLED", "0").lower()
        in {"1", "true", "yes", "on", "evet", "aktif"},
        "YAZKLINIK_PATIENT_PORTAL_ENABLED",
    )
    c.expect(
        "portal base host hasta subdomain",
        base_host == PATIENT_HOST,
        base_url,
    )
    c.expect(
        "cloudflared ingress 5053",
        cloudflared_has_patient_ingress(cloudflared_config_path()),
        str(cloudflared_config_path()),
    )

    token = ""
    try:
        token = create_test_token(db_file)
        c.ok("gecici test token olusturuldu", "tail=" + token[-8:])

        require_status(
            c,
            "ana login normal acik",
            f"{LOCAL_MAIN}/giris",
            200,
            attempts=45,
        )
        require_status(
            c,
            "hasta host ana login'i kilitli",
            f"{LOCAL_MAIN}/giris",
            404,
            host=PATIENT_HOST,
            attempts=45,
        )
        require_status(
            c,
            "hasta portal health",
            f"{LOCAL_PATIENT}/healthz",
            200,
            contains="patient_portal_public",
        )
        require_status(
            c,
            "hasta portal login yok",
            f"{LOCAL_PATIENT}/giris",
            404,
            host=PATIENT_HOST,
        )
        require_status(
            c,
            "hasta portal sistem ayari yok",
            f"{LOCAL_PATIENT}/sistem-ayarlari",
            404,
            host=PATIENT_HOST,
        )

        old_path = f"{LOCAL_MAIN}/hasta-portal/p/{token}"
        status, headers, _body = require_status(
            c,
            "ana eski portal yolu yonlenir",
            old_path,
            302,
            attempts=45,
        )
        location = headers.get("Location", "")
        if status == 302:
            c.expect(
                "yonlendirme hasta subdomain'e",
                location.startswith(f"https://{PATIENT_HOST}/hasta-portal/p/"),
                location,
            )
        require_status(
            c,
            "hasta host ana token yolunda kapali",
            old_path,
            404,
            host=PATIENT_HOST,
            attempts=45,
        )
        require_status(
            c,
            "lokal ayri portal token acik",
            f"{LOCAL_PATIENT}/hasta-portal/p/{token}",
            200,
            host=PATIENT_HOST,
            header_contains=("Cache-Control", "no-store"),
        )

        if not args.local_only:
            require_status(
                c,
                "public hasta portal ana sayfa",
                PATIENT_PUBLIC,
                200,
                attempts=12,
            )
            require_status(
                c,
                "public hasta portal login kapali",
                PATIENT_PUBLIC + "giris",
                404,
                attempts=12,
            )
            require_status(
                c,
                "public main ana domain ayri",
                MAIN_PUBLIC,
                {200, 302},
                attempts=20,
            )
            require_status(
                c,
                "public token ayri portalda acik",
                PATIENT_PUBLIC + f"hasta-portal/p/{token}",
                200,
                header_contains=("Cache-Control", "no-store"),
                attempts=12,
            )
    finally:
        if token:
            revoke_test_token(db_file, token)
            c.ok("gecici test token iptal edildi", "tail=" + token[-8:])

    require_status(
        c,
        "iptal token artik kapali",
        f"{LOCAL_PATIENT}/hasta-portal/p/{token}",
        403,
        host=PATIENT_HOST,
    )

    print("=" * 56)
    print(f"Hata: {c.failed} | Uyari: {c.warned}")
    if c.failed:
        print("D700_PATIENT_PORTAL_SPLIT_CHECK_FAIL")
        return 1
    print("D700_PATIENT_PORTAL_SPLIT_CHECK_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
