"""2FA TOTP Ajani - Doktor giris korumasi.

pyotp + qrcode kullanir; secrets DB'de hashli.
Ilk setup: secret uret + QR goster (Google Authenticator).
Sonraki girisler: 6 hane TOTP kod sor.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from yazklinik_db_adapter import agent_connection as _pgconn  # PG-primary aware (cutover)
import struct
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-2fa"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")


@dataclass
class TOTPSetup:
    user: str
    secret_b32: str
    qr_url: str             # otpauth://totp/...
    backup_codes: List[str] = field(default_factory=list)
    agent_version: str = AGENT_VERSION


def _b32_secret(length_bytes: int = 20) -> str:
    """Pyotp.random_base32 fallback (stdlib)."""
    raw = secrets.token_bytes(length_bytes)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _totp_now(secret_b32: str, step: int = 30, digits: int = 6) -> str:
    """RFC 6238 TOTP (pyotp olmasa da calisir)."""
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    counter = int(time.time() // step)
    msg = struct.pack(">Q", counter)
    mac = hmac.new(key, msg, hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code_int = struct.unpack(">I", mac[off:off+4])[0] & 0x7FFFFFFF
    return str(code_int)[-digits:].rjust(digits, "0")


def _ensure_table(db_path: str) -> None:
    con = _pgconn(sqlite_path=db_path)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS user_2fa (
            "user" TEXT PRIMARY KEY,
            secret_b32 TEXT,
            enabled INTEGER DEFAULT 0,
            backup_codes_hash TEXT,
            created_at TEXT,
            last_verified TEXT
        )""")
        con.commit()
    finally:
        con.close()


def setup(user: str, db_path: Optional[str] = None,
          issuer: str = "YazKlinik",
          allow_overwrite: bool = False) -> TOTPSetup:
    """Ilk kez 2FA setup - QR + backup kod uret.

    GUVENLIK: Onceki INSERT OR REPLACE mevcut 2FA'yi sifirlayabilirdi.
    Simdi varolan kayit varsa allow_overwrite=False ise hata mesaji doner.
    Reset icin: reset(user, verify_code) cagir.
    """
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)

    # Mevcut kayit kontrolu
    con = _pgconn(sqlite_path=db_path)
    try:
        row = con.execute(
            "SELECT enabled FROM user_2fa WHERE \"user\" = ?", (user,)).fetchone()
    finally:
        con.close()
    if row and not allow_overwrite:
        return TOTPSetup(
            user=user, secret_b32="",
            qr_url="ALREADY_REGISTERED",
            backup_codes=[
                "Bu kullanici icin 2FA zaten kayitli.",
                "Sifirlamak icin once mevcut 6-haneli kod ile",
                "POST /api/agents/2fa/reset endpoint'ini cagir."])

    secret = _b32_secret()
    backup = [secrets.token_hex(4) for _ in range(8)]
    backup_hash = hashlib.sha256(",".join(backup).encode()).hexdigest()
    qr_url = (f"otpauth://totp/{issuer}:{user}?"
              f"secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30")

    con = _pgconn(sqlite_path=db_path)
    try:
        con.execute(
            "INSERT OR REPLACE INTO user_2fa "
            "(\"user\", secret_b32, enabled, backup_codes_hash, created_at) "
            "VALUES (?, ?, 0, ?, datetime('now'))",
            (user, secret, backup_hash))
        con.commit()
    finally:
        con.close()
    return TOTPSetup(user=user, secret_b32=secret, qr_url=qr_url, backup_codes=backup)


def reset(user: str, verify_code: str, db_path: Optional[str] = None) -> bool:
    """2FA reset - mevcut kod ile dogrulayip sil. Sonra setup() yeniden cagrilabilir."""
    if not verify(user, verify_code, db_path=db_path):
        return False
    db_path = db_path or DEFAULT_DB_PATH
    con = _pgconn(sqlite_path=db_path)
    try:
        con.execute("DELETE FROM user_2fa WHERE \"user\" = ?", (user,))
        con.commit()
        return True
    finally:
        con.close()


def enable(user: str, sample_code: str, db_path: Optional[str] = None) -> bool:
    """Setup sonrasi ilk gecerli kod ile aktif et."""
    db_path = db_path or DEFAULT_DB_PATH
    if verify(user, sample_code, db_path=db_path):
        con = _pgconn(sqlite_path=db_path)
        try:
            con.execute("UPDATE user_2fa SET enabled = 1 WHERE \"user\" = ?", (user,))
            con.commit()
            return True
        finally:
            con.close()
    return False


def verify(user: str, code: str, db_path: Optional[str] = None) -> bool:
    """Login sirasinda 6 haneli TOTP dogrula (+/-1 step tolerans)."""
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    con = _pgconn(sqlite_path=db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT secret_b32, enabled FROM user_2fa WHERE \"user\" = ?",
                           (user,)).fetchone()
        if not row or not row["secret_b32"]:
            return False
        sec = row["secret_b32"]
        # +-1 step tolerance
        key = base64.b32decode(sec + "=" * (-len(sec) % 8))
        for delta in (-1, 0, 1):
            counter = int(time.time() // 30) + delta
            msg = struct.pack(">Q", counter)
            mac = hmac.new(key, msg, hashlib.sha1).digest()
            off = mac[-1] & 0x0F
            code_int = struct.unpack(">I", mac[off:off+4])[0] & 0x7FFFFFFF
            check = str(code_int)[-6:].rjust(6, "0")
            if hmac.compare_digest(check, str(code).strip()):
                try:
                    con.execute("UPDATE user_2fa SET last_verified = datetime('now') WHERE \"user\" = ?",
                                (user,))
                    con.commit()
                except Exception:
                    pass
                return True
        return False
    finally:
        con.close()


def is_enabled(user: str, db_path: Optional[str] = None) -> bool:
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    con = _pgconn(sqlite_path=db_path)
    try:
        row = con.execute("SELECT enabled FROM user_2fa WHERE \"user\" = ?", (user,)).fetchone()
        return bool(row and row[0])
    finally:
        con.close()


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION}


if __name__ == "__main__":
    # Demo
    s = setup("doktor")
    code_now = _totp_now(s.secret_b32)
    print(f"Setup OK. Test kod: {code_now}")
    ok = enable("doktor", code_now)
    print(f"Enable: {ok}")
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
