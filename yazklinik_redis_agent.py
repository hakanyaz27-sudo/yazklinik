"""Redis Ajani - cache + kuyruk wrapper.

Kullanim alanlari:
    - sesli_onay onay kuyrugu (pending appointment ID'ler)
    - geri_cagirma scheduled jobs
    - telesekreter triage cache (yeni gelen caller'lar)
    - Alex sesli session memory (TTL 30 dk)
    - API rate limit (login attempts)

Default: lazy connect, hicbir kod bunu zorunlu hale getirmiyor.
Redis down ise cache miss = SQLite/disk fallback.

Env:
    YAZKLINIK_REDIS_URL  veya
    REDIS_PASSWORD (akillilik/.env'den okur)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-redis"
ROOT = Path(__file__).resolve().parent


def _load_env_file(path: str = "") -> Dict[str, str]:
    if not path:
        candidates = [
            os.environ.get("YAZKLINIK_AKILLILIK_ENV") or "",
            str(ROOT / "akillilik" / ".env"),
            r"D:\YazKlinik_Final_D700\akillilik\.env",
            r"D:\YazKlinik_Final_D500\akillilik\.env",
        ]
        path = next((p for p in candidates if p and Path(p).exists()), "")
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except Exception:
        pass
    return out


def _url(host: str = "localhost", port: int = 16379) -> str:
    explicit = os.environ.get("YAZKLINIK_REDIS_URL") or os.environ.get("REDIS_URL")
    if explicit:
        return explicit
    pw = os.environ.get("REDIS_PASSWORD") or _load_env_file().get("REDIS_PASSWORD", "")
    if not pw:
        pw = "CHANGE_yk_redis"
    return f"redis://:{pw}@{host}:{port}/0"


_client = None


def get_client():
    """Lazy global Redis client. None donerse Redis erisilmez."""
    global _client
    if _client is not None:
        return _client
    try:
        import redis
        _client = redis.Redis.from_url(_url(), decode_responses=True,
                                         socket_connect_timeout=2, socket_timeout=3)
        _client.ping()
    except Exception:
        _client = None
    return _client


def health_check() -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": False, "agent_version": AGENT_VERSION,
                              "url_host": "localhost", "url_port": 16379}
    c = get_client()
    if c is None:
        out["error"] = "Redis erisilmez"
        return out
    try:
        info = c.info(section="server")
        out["ok"] = True
        out["redis_version"] = info.get("redis_version")
        out["uptime_sec"] = info.get("uptime_in_seconds")
        out["memory_used_human"] = c.info(section="memory").get("used_memory_human")
    except Exception as e:
        out["error"] = str(e)
    return out


# --- Cache (KV with TTL) ---

def cache_set(key: str, value: Any, ttl_sec: int = 3600) -> bool:
    c = get_client()
    if not c:
        return False
    try:
        v = json.dumps(value, ensure_ascii=False, default=str)
        return bool(c.set(name=f"yk:cache:{key}", value=v, ex=int(ttl_sec)))
    except Exception:
        return False


def cache_get(key: str, default=None) -> Any:
    c = get_client()
    if not c:
        return default
    try:
        v = c.get(f"yk:cache:{key}")
        if v is None:
            return default
        return json.loads(v)
    except Exception:
        return default


def cache_delete(key: str) -> bool:
    c = get_client()
    if not c:
        return False
    try:
        return bool(c.delete(f"yk:cache:{key}"))
    except Exception:
        return False


# --- Kuyruk (LIST tabanli, FIFO) ---

def queue_push(queue_name: str, item: Any) -> bool:
    """Kuyruga sona ekle. Item JSON serialize edilir."""
    c = get_client()
    if not c:
        return False
    try:
        c.rpush(f"yk:q:{queue_name}",
                  json.dumps(item, ensure_ascii=False, default=str))
        return True
    except Exception:
        return False


def queue_pop(queue_name: str, timeout: int = 0) -> Optional[Any]:
    """Bastan al (FIFO). timeout=0 anlik, >0 blocking saniye."""
    c = get_client()
    if not c:
        return None
    try:
        if timeout > 0:
            r = c.blpop(f"yk:q:{queue_name}", timeout=int(timeout))
            if not r:
                return None
            _, v = r
        else:
            v = c.lpop(f"yk:q:{queue_name}")
            if not v:
                return None
        return json.loads(v)
    except Exception:
        return None


def queue_length(queue_name: str) -> int:
    c = get_client()
    if not c:
        return -1
    try:
        return int(c.llen(f"yk:q:{queue_name}"))
    except Exception:
        return -1


def queue_peek(queue_name: str, limit: int = 10) -> List[Any]:
    c = get_client()
    if not c:
        return []
    try:
        raw = c.lrange(f"yk:q:{queue_name}", 0, int(limit) - 1)
        return [json.loads(v) for v in raw]
    except Exception:
        return []


# --- Sesli onay icin yardimcilar (sik kullanilan) ---

def push_voice_confirm_pending(appointment_id: str, payload: Dict[str, Any],
                                ttl_sec: int = 86400) -> bool:
    """Bekleyen sesli onayi 24 saat cache'le."""
    return cache_set(f"voice_confirm:{appointment_id}", payload, ttl_sec=ttl_sec)


def pop_voice_confirm_pending(appointment_id: str) -> Optional[Dict[str, Any]]:
    v = cache_get(f"voice_confirm:{appointment_id}")
    if v is not None:
        cache_delete(f"voice_confirm:{appointment_id}")
    return v


# --- Rate limit ---

def rate_limit_hit(key: str, window_sec: int = 60, max_count: int = 30) -> bool:
    """True dondurursa: ALLOWED. False: rate limited."""
    c = get_client()
    if not c:
        return True  # Redis yoksa kapalı
    try:
        k = f"yk:rate:{key}"
        cur = c.incr(k)
        if cur == 1:
            c.expire(k, int(window_sec))
        return cur <= int(max_count)
    except Exception:
        return True


# --- Session memory (Alex) ---

def session_add(session_id: str, key: str, value: Any, ttl_sec: int = 1800) -> bool:
    c = get_client()
    if not c:
        return False
    try:
        c.hset(f"yk:session:{session_id}", key,
                 json.dumps(value, ensure_ascii=False, default=str))
        c.expire(f"yk:session:{session_id}", int(ttl_sec))
        return True
    except Exception:
        return False


def session_get_all(session_id: str) -> Dict[str, Any]:
    c = get_client()
    if not c:
        return {}
    try:
        raw = c.hgetall(f"yk:session:{session_id}")
        return {k: json.loads(v) for k, v in raw.items()}
    except Exception:
        return {}


if __name__ == "__main__":
    print("HEALTH:", json.dumps(health_check(), ensure_ascii=False, indent=2))
    # Mini smoke
    print("\nCache test:")
    cache_set("test", {"x": 1, "t": time.time()}, ttl_sec=60)
    print("  set+get:", cache_get("test"))
    print("\nQueue test:")
    queue_push("test_q", {"job": "test1"})
    queue_push("test_q", {"job": "test2"})
    print("  length:", queue_length("test_q"))
    print("  pop1:", queue_pop("test_q"))
    print("  length:", queue_length("test_q"))
    cache_delete("test")
    queue_pop("test_q")  # temizlik
    print("\nRate limit:")
    for i in range(5):
        print(f"  hit {i+1}:", rate_limit_hit("test_user", window_sec=60, max_count=3))
