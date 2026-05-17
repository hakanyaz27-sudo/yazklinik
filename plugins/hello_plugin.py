"""Hello Plugin - YazKlinik plugin sistemi demo.

Bu dosya plugins/ klasorune konursa, plugin_loader otomatik yukler.

Plugin sablon:
    - AGENT_VERSION (string)
    - health_check() (dict doner)
    - Public callable'lar (snake_case, _ ile baslamayan)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List


AGENT_VERSION = "2026.05.17-hello-plugin-1.0"


@dataclass
class GreetingResult:
    name: str
    greeting: str
    timestamp: str
    plugin: str = "hello_plugin"


def greet(name: str = "Doktor") -> Dict[str, Any]:
    """Bir kisiyi selamla. Plugin'in ana fonksiyonu."""
    return asdict(GreetingResult(
        name=name,
        greeting=f"Merhaba {name}, YazKlinik plugin sistemi calisiyor!",
        timestamp=datetime.now().isoformat(timespec="seconds")))


def list_capabilities() -> List[str]:
    """Bu plugin neler yapabilir?"""
    return [
        "Selamlama mesaji uretir",
        "Plugin sisteminin calistigini gosterir",
        "Yeni plugin'ler icin sablondur",
    ]


def calculate(a: float, b: float, op: str = "+") -> Dict[str, Any]:
    """Basit hesap (4 islem)."""
    ops = {"+": lambda x, y: x + y, "-": lambda x, y: x - y,
            "*": lambda x, y: x * y, "/": lambda x, y: x / y if y else None}
    fn = ops.get(op)
    if not fn:
        return {"ok": False, "error": f"Bilinmeyen islem: {op}"}
    return {"ok": True, "result": fn(a, b), "op": op, "a": a, "b": b}


def health_check() -> Dict[str, Any]:
    return {"ok": True, "plugin": "hello_plugin",
            "version": AGENT_VERSION,
            "functions": ["greet", "list_capabilities", "calculate"]}


if __name__ == "__main__":
    print(json.dumps(greet("Hakan"), ensure_ascii=False, indent=2))
    print(json.dumps(list_capabilities(), ensure_ascii=False, indent=2))
    print(json.dumps(calculate(15, 3, "*"), ensure_ascii=False, indent=2))
