"""Plugin Loader - 3. taraf ajan dinamik yukleme.

plugins/ klasorundeki .py dosyalarini tarar + register eder.
Her plugin AGENT_VERSION + health_check() + en az bir public fonksiyon icermeli.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


AGENT_VERSION = "2026.05.17-plugin-loader"

PLUGINS_DIR = (os.environ.get("YAZKLINIK_PLUGINS_DIR")
                or r"D:\YazKlinik_Final_D500\plugins")


@dataclass
class PluginInfo:
    name: str
    path: str
    version: str = ""
    loaded: bool = False
    health: Dict[str, Any] = field(default_factory=dict)
    public_callables: List[str] = field(default_factory=list)
    error: str = ""


@dataclass
class PluginRegistry:
    plugins: Dict[str, PluginInfo] = field(default_factory=dict)
    last_scan: str = ""
    agent_version: str = AGENT_VERSION


_registry = PluginRegistry()


def scan_and_load(force: bool = False) -> PluginRegistry:
    """plugins/ klasorunu tara, modulleri import et."""
    if not os.path.isdir(PLUGINS_DIR):
        os.makedirs(PLUGINS_DIR, exist_ok=True)
    _registry.last_scan = datetime.now().isoformat(timespec="seconds")

    for fname in os.listdir(PLUGINS_DIR):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        full = os.path.join(PLUGINS_DIR, fname)
        mod_name = "yazklinik_plugin_" + fname[:-3]
        info = PluginInfo(name=fname[:-3], path=full)
        try:
            if mod_name in sys.modules and not force:
                mod = sys.modules[mod_name]
            else:
                spec = importlib.util.spec_from_file_location(mod_name, full)
                if not spec or not spec.loader:
                    raise ImportError("spec uretilemedi")
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
            info.version = getattr(mod, "AGENT_VERSION", "")
            info.loaded = True
            # health_check?
            hc = getattr(mod, "health_check", None)
            if callable(hc):
                try:
                    info.health = hc() or {}
                except Exception as e:
                    info.health = {"error": str(e)}
            # Public callables
            info.public_callables = sorted([
                k for k, v in vars(mod).items()
                if callable(v) and not k.startswith("_") and k not in ("health_check",)
            ])
        except Exception as e:
            info.error = f"{type(e).__name__}: {e}"
        _registry.plugins[info.name] = info
    return _registry


def list_plugins() -> List[Dict[str, Any]]:
    return [asdict(p) for p in _registry.plugins.values()]


def call_plugin(plugin_name: str, func_name: str, *args, **kwargs) -> Any:
    """Plugin'in bir fonksiyonunu cagir."""
    mod_name = "yazklinik_plugin_" + plugin_name
    mod = sys.modules.get(mod_name)
    if not mod:
        scan_and_load()
        mod = sys.modules.get(mod_name)
    if not mod:
        return {"ok": False, "error": "plugin yuklenmedi"}
    fn = getattr(mod, func_name, None)
    if not callable(fn):
        return {"ok": False, "error": f"fonksiyon yok: {func_name}"}
    try:
        return {"ok": True, "result": fn(*args, **kwargs)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "plugins_dir": PLUGINS_DIR,
            "loaded_count": len(_registry.plugins)}


if __name__ == "__main__":
    r = scan_and_load()
    print(json.dumps({"count": len(r.plugins),
                       "plugins": list_plugins()},
                       ensure_ascii=False, indent=2))
