"""Stok Takip Ajani - Klinik malzeme + ilac stok yonetimi.

Otomatik:
    - Bitmek uzere olanlari uyar
    - Son kullanma tarihi yaklasanlari uyar
    - Aylik sarfiyat tahmin
    - Tedarikci e-postasi taslagi
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-stok"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")


@dataclass
class StockItem:
    code: str
    name: str
    category: str          # ilac | sarf | cihaz | egitim
    quantity_on_hand: int = 0
    reorder_threshold: int = 5
    expiry_date: Optional[str] = None
    supplier: str = ""
    last_used: Optional[str] = None
    cost_per_unit: float = 0.0


@dataclass
class StockAlert:
    item_code: str
    item_name: str
    alert_type: str        # low_stock | expiring_soon | expired | reorder_now
    message: str
    severity: str          # info | warning | critical
    suggested_action: str = ""


@dataclass
class StockReport:
    generated_at: str
    total_items: int = 0
    total_value_try: float = 0
    alerts: List[StockAlert] = field(default_factory=list)
    items: List[Dict[str, Any]] = field(default_factory=list)
    monthly_consumption_estimate: Dict[str, int] = field(default_factory=dict)
    agent_version: str = AGENT_VERSION


def _ensure_table(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS stock_items (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            quantity_on_hand INTEGER DEFAULT 0,
            reorder_threshold INTEGER DEFAULT 5,
            expiry_date TEXT,
            supplier TEXT,
            last_used TEXT,
            cost_per_unit REAL DEFAULT 0,
            updated_at TEXT
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_code TEXT,
            direction TEXT,    -- in | out
            quantity INTEGER,
            note TEXT,
            ts TEXT
        )""")
        con.commit()
    finally:
        con.close()


def upsert_item(item: StockItem, db_path: Optional[str] = None) -> bool:
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "INSERT OR REPLACE INTO stock_items "
            "(code, name, category, quantity_on_hand, reorder_threshold, "
            " expiry_date, supplier, last_used, cost_per_unit, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (item.code, item.name, item.category, item.quantity_on_hand,
             item.reorder_threshold, item.expiry_date, item.supplier,
             item.last_used, item.cost_per_unit))
        con.commit()
        return True
    except Exception:
        return False
    finally:
        con.close()


def record_movement(code: str, direction: str, quantity: int,
                     note: str = "", db_path: Optional[str] = None) -> bool:
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "INSERT INTO stock_movements (item_code, direction, quantity, note, ts) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (code, direction, quantity, note))
        # Update on-hand
        if direction == "in":
            con.execute(
                "UPDATE stock_items SET quantity_on_hand = quantity_on_hand + ? WHERE code = ?",
                (quantity, code))
        else:
            con.execute(
                "UPDATE stock_items SET quantity_on_hand = MAX(0, quantity_on_hand - ?), "
                "last_used = datetime('now') WHERE code = ?",
                (quantity, code))
        con.commit()
        return True
    except Exception:
        return False
    finally:
        con.close()


def generate_report(db_path: Optional[str] = None) -> StockReport:
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    rpt = StockReport(generated_at=datetime.now().isoformat(timespec="seconds"))

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT * FROM stock_items").fetchall()
        rpt.total_items = len(rows)
        for r in rows:
            rpt.items.append({
                "code": r["code"],
                "name": r["name"],
                "category": r["category"],
                "quantity_on_hand": int(r["quantity_on_hand"] or 0),
                "reorder_threshold": int(r["reorder_threshold"] or 0),
                "expiry_date": r["expiry_date"] or "",
                "supplier": r["supplier"] or "",
                "cost_per_unit": float(r["cost_per_unit"] or 0),
            })
            rpt.total_value_try += float(r["quantity_on_hand"] or 0) * float(r["cost_per_unit"] or 0)

            # Low stock?
            if (r["quantity_on_hand"] or 0) <= (r["reorder_threshold"] or 5):
                rpt.alerts.append(StockAlert(
                    item_code=r["code"], item_name=r["name"],
                    alert_type="low_stock", severity="warning",
                    message=f"{r['name']}: {r['quantity_on_hand']} adet kaldı "
                            f"(eşik: {r['reorder_threshold']})",
                    suggested_action=f"{r['supplier'] or 'Tedarikçi'}'den sipariş ver"))

            # Expiry?
            exp = r["expiry_date"]
            if exp:
                try:
                    exp_d = datetime.fromisoformat(exp).date()
                    days_left = (exp_d - date.today()).days
                    if days_left < 0:
                        rpt.alerts.append(StockAlert(
                            item_code=r["code"], item_name=r["name"],
                            alert_type="expired", severity="critical",
                            message=f"{r['name']} {abs(days_left)} gün önce miatlı geçti",
                            suggested_action="İmha et / iade"))
                    elif days_left <= 30:
                        rpt.alerts.append(StockAlert(
                            item_code=r["code"], item_name=r["name"],
                            alert_type="expiring_soon", severity="warning",
                            message=f"{r['name']} {days_left} gün sonra miatı doluyor",
                            suggested_action="Önce kullan / iade düşün"))
                except Exception:
                    pass

        # Aylik tuketim tahmini
        mov_rows = con.execute(
            "SELECT item_code, SUM(quantity) AS total_out "
            "FROM stock_movements WHERE direction = 'out' "
            "AND ts >= datetime('now', '-30 days') GROUP BY item_code"
        ).fetchall()
        for m in mov_rows:
            rpt.monthly_consumption_estimate[m["item_code"]] = int(m["total_out"] or 0)
    finally:
        con.close()

    rpt.total_value_try = round(rpt.total_value_try, 2)
    return rpt


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION}


if __name__ == "__main__":
    upsert_item(StockItem(
        code="OXY-10IU", name="Oxytocin 10IU/ml ampul", category="ilac",
        quantity_on_hand=12, reorder_threshold=10,
        expiry_date=(date.today() + timedelta(days=20)).isoformat(),
        supplier="Pfizer", cost_per_unit=45.0))
    r = generate_report()
    print(json.dumps(asdict(r), ensure_ascii=False, indent=2))
