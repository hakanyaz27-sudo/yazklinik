"""IoT Bluetooth Cihaz Ajani - Tansiyon, Tarti, Glukometre.

Bluetooth LE cihazlardan otomatik olcum okur + hasta dosyasina yazar.
Stub mode: simulate gerek; production icin bleak (python BLE) gerekir.

Desteklenen ornek cihazlar (model bazli):
    - Omron HEM-7361T (tansiyon)
    - Xiaomi Mi Body Scale 2 (tarti)
    - Accu-Chek Aviva Connect (glukoz)
"""
from __future__ import annotations

import json
import os
import sqlite3
from yazklinik_db_adapter import agent_connection as _pgconn  # PG-primary aware (cutover)
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-iot-bt"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")


@dataclass
class IoTReading:
    device_type: str       # bp | scale | glucose
    device_model: str
    patient_id: str
    measured_at: str
    values: Dict[str, Any] = field(default_factory=dict)
    raw_packet: str = ""


@dataclass
class ScanResult:
    devices_found: List[Dict[str, str]] = field(default_factory=list)
    backend_available: bool = False
    error: str = ""
    agent_version: str = AGENT_VERSION


def _backend_available() -> bool:
    try:
        import bleak  # noqa: F401
        return True
    except Exception:
        return False


def scan_for_devices(timeout_sec: int = 5) -> ScanResult:
    """Yakindaki BT cihazlari tara (stub - production bleak gerek)."""
    res = ScanResult(backend_available=_backend_available())
    if not res.backend_available:
        res.error = "bleak paketi yok. pip install bleak ile kur."
        return res
    # Production:
    #   from bleak import BleakScanner
    #   devs = await BleakScanner.discover(timeout_sec)
    res.devices_found = [
        {"name": "STUB: Omron 7361T", "address": "00:1A:7D:DA:71:13"},
    ]
    return res


def parse_omron_bp(packet_hex: str) -> Dict[str, int]:
    """Omron BLE tansiyon paketi (sistol/diyastol/nabiz)."""
    try:
        b = bytes.fromhex(packet_hex.replace(" ", ""))
        if len(b) >= 7:
            return {"systolic": b[1], "diastolic": b[3], "pulse": b[5]}
    except Exception:
        pass
    return {}


def parse_xiaomi_scale(packet_hex: str) -> Dict[str, float]:
    """Xiaomi tarti paketi (kg + impedance).

    FIX: Onceki outer kontrolu len(b) >= 10 idi ama b[11:13] icin
    len(b) >= 13 gerek. 10-12 byte paket gelirse weight=0.0 doner sessiz hata.
    Simdi tek bound check (>= 13).
    """
    try:
        b = bytes.fromhex(packet_hex.replace(" ", ""))
        if len(b) >= 13:
            weight_raw = int.from_bytes(b[11:13], "little")
            return {"weight_kg": round(weight_raw * 0.005, 2)}
    except Exception:
        pass
    return {}


def save_reading(reading: IoTReading, db_path: Optional[str] = None) -> bool:
    db_path = db_path or DEFAULT_DB_PATH
    con = _pgconn(sqlite_path=db_path)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS iot_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_type TEXT,
            device_model TEXT,
            patient_id TEXT,
            measured_at TEXT,
            values_json TEXT,
            raw_packet TEXT,
            ingested_at TEXT
        )""")
        con.execute(
            "INSERT INTO iot_readings (device_type, device_model, patient_id, "
            "measured_at, values_json, raw_packet, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (reading.device_type, reading.device_model, reading.patient_id,
             reading.measured_at, json.dumps(reading.values), reading.raw_packet))
        con.commit()
        return True
    except Exception:
        return False
    finally:
        con.close()


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "bleak_backend": _backend_available()}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
