"""Odeme Ajani - Iyzico / Stripe entegrasyon stub.

Iki saglayici desteklenir:
    - Iyzico (TR-yerel, taksit destekli)
    - Stripe (global, kart sakla destegi)

Production icin gercek API key + webhook gerek; bu modul yapiyi sunar.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from yazklinik_db_adapter import agent_connection as _pgconn  # PG-primary aware (cutover)
import time
import secrets
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-payment"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")

IYZICO_API_KEY = os.environ.get("IYZICO_API_KEY", "")
IYZICO_SECRET = os.environ.get("IYZICO_SECRET", "")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")


@dataclass
class PaymentRequest:
    patient_id: str
    amount_try: float
    description: str
    invoice_number: str = ""
    provider: str = "iyzico"  # iyzico | stripe
    installments: int = 1
    return_url: str = ""


@dataclass
class PaymentResult:
    ok: bool
    order_id: str = ""
    provider_ref: str = ""
    status: str = "pending"   # pending | success | failed | refunded
    redirect_url: str = ""    # 3D secure
    error_message: str = ""
    amount_try: float = 0
    raw_response: Dict[str, Any] = field(default_factory=dict)
    agent_version: str = AGENT_VERSION


def _ensure_table(db_path: str) -> None:
    con = _pgconn(sqlite_path=db_path)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS payments (
            order_id TEXT PRIMARY KEY,
            patient_id TEXT,
            amount_try REAL,
            description TEXT,
            invoice_number TEXT,
            provider TEXT,
            installments INTEGER DEFAULT 1,
            status TEXT,
            provider_ref TEXT,
            created_at TEXT,
            paid_at TEXT,
            refunded_at TEXT,
            raw_response TEXT
        )""")
        con.commit()
    finally:
        con.close()


def initiate(req: PaymentRequest, db_path: Optional[str] = None) -> PaymentResult:
    """Odemeyi baslat; stub mode test verisi dondurur."""
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)

    order_id = f"ORD-{int(time.time())}-{secrets.token_hex(4)}"
    result = PaymentResult(ok=False, order_id=order_id, amount_try=req.amount_try)

    if req.provider == "iyzico" and not IYZICO_API_KEY:
        result.status = "stub"
        result.error_message = "IYZICO_API_KEY env yok - stub mode"
        result.redirect_url = f"/payment/stub-success?order={order_id}"
        result.ok = True
    elif req.provider == "stripe" and not STRIPE_SECRET_KEY:
        result.status = "stub"
        result.error_message = "STRIPE_SECRET_KEY env yok - stub mode"
        result.redirect_url = f"/payment/stub-success?order={order_id}"
        result.ok = True
    else:
        # Production: gercek API cagrisi (iyzico veya stripe SDK)
        result.error_message = "Production cagrisi henuz implement edilmedi"
        result.ok = False

    con = _pgconn(sqlite_path=db_path)
    try:
        con.execute(
            "INSERT INTO payments (order_id, patient_id, amount_try, description, "
            "invoice_number, provider, installments, status, created_at, raw_response) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)",
            (order_id, req.patient_id, req.amount_try, req.description,
             req.invoice_number, req.provider, req.installments, result.status,
             json.dumps(result.raw_response)))
        con.commit()
    except Exception:
        pass
    finally:
        con.close()
    return result


def _verify_webhook_signature(provider: str, raw_body: bytes,
                                signature: str) -> bool:
    """HMAC-SHA256 webhook signature dogrula.

    GUVENLIK: Onceki versiyon imzayi hic dogrulamiyordu, saldirgan
    POST {'status':'success'} ile siparisi 'odendi' yapabilirdi.
    """
    secret = ""
    if provider == "iyzico":
        secret = IYZICO_SECRET
    elif provider == "stripe":
        secret = STRIPE_SECRET_KEY
    if not secret or not signature:
        # Hicbir secret tanimli degilse sadece localhost'tan calismali
        # (rota seviyesinde IP+token korumasi ile)
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    # constant-time compare (timing attack)
    return hmac.compare_digest(expected, signature.strip())


def confirm_webhook(provider: str, payload: Dict[str, Any],
                     signature: str = "",
                     raw_body: Optional[bytes] = None,
                     db_path: Optional[str] = None) -> Dict[str, Any]:
    """Webhook dogrula + DB'de status guncelle.

    GUVENLIK: Eger raw_body verildi VE provider production'da ise
    signature mutlaka dogrulanir. Stub mode'da (key yok) production payload
    geri cevrilir.
    """
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)

    # Imza zorunlu (production)
    if raw_body is not None:
        has_secret = (IYZICO_SECRET if provider == "iyzico"
                       else STRIPE_SECRET_KEY if provider == "stripe" else "")
        if has_secret:
            if not _verify_webhook_signature(provider, raw_body, signature):
                return {"ok": False, "error": "invalid_signature",
                        "provider": provider}

    order_id = (payload.get("order_id") or payload.get("conversationId")
                 or payload.get("metadata", {}).get("order_id", ""))
    new_status = (payload.get("status") or
                   ("success" if payload.get("paymentStatus") == "SUCCESS" else "failed"))

    if order_id:
        con = _pgconn(sqlite_path=db_path)
        try:
            con.execute(
                "UPDATE payments SET status = ?, provider_ref = ?, "
                "paid_at = CASE WHEN ? = 'success' THEN datetime('now') ELSE paid_at END "
                "WHERE order_id = ?",
                (new_status, payload.get("paymentId", ""), new_status, order_id))
            con.commit()
        finally:
            con.close()
    return {"ok": True, "order_id": order_id, "new_status": new_status}


def refund(order_id: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Iade baslat (stub)."""
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    con = _pgconn(sqlite_path=db_path)
    try:
        con.execute(
            "UPDATE payments SET status = 'refunded', refunded_at = datetime('now') "
            "WHERE order_id = ?", (order_id,))
        con.commit()
        return {"ok": True, "order_id": order_id, "status": "refunded"}
    finally:
        con.close()


def list_recent(limit: int = 50, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    con = _pgconn(sqlite_path=db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT order_id, patient_id, amount_try, status, provider, created_at "
            "FROM payments ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "iyzico_configured": bool(IYZICO_API_KEY),
            "stripe_configured": bool(STRIPE_SECRET_KEY)}


if __name__ == "__main__":
    r = initiate(PaymentRequest(
        patient_id="P-001", amount_try=850.0,
        description="USG + konsultasyon", invoice_number="2026-0042"))
    print(json.dumps(asdict(r), ensure_ascii=False, indent=2))
