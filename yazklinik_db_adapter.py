#!/usr/bin/env python
"""Database runtime adapter scaffold for YazKlinik D700.

This module is the safe bridge for the SQLite -> PostgreSQL cutover.
It does not change the live app by itself. It centralizes mode detection,
guard checks, PostgreSQL connections, and SQLite-maintenance safety rules so
the old direct sqlite3.connect sites can be replaced one by one.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional
from urllib.parse import urlsplit, urlunsplit

import yazklinik_sql_dialect as sql_dialect


ROOT = Path(__file__).resolve().parent
CONFIG_ENV = ROOT / "config.env"
DEFAULT_SQLITE_PATH = ROOT / "local_db" / "yazklinik_v68.sqlite3"
ADAPTER_VERSION = "2026.05.19-db-adapter-scaffold"
_DEFAULT_ISOLATION = object()


def load_config_env(path: Path = CONFIG_ENV) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        existing = os.environ.get(key)
        # Runtime servis bazen degiskeni BOS ("") tasiyor; bu durumda da
        # config.env degerini yuklemek gerekir.
        if existing is None or str(existing).strip() == "":
            os.environ[key] = value.strip()


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _norm(os.environ.get(key, "1" if default else "0"))
    return raw in {"1", "true", "yes", "y", "on"}


def _allow_sqlite_fallback_on_pg_block() -> bool:
    """PG-primary istenip hazirlik bloklandiginda runtime'i dusurmeden devam et."""
    return _env_bool("YAZKLINIK_ALLOW_SQLITE_FALLBACK_ON_PG_BLOCK", True)


def _postgres_dsn() -> str:
    explicit = os.environ.get("YAZKLINIK_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "15432")
    user = os.environ.get("POSTGRES_USER", "yazklinik")
    pwd = os.environ.get("POSTGRES_PASSWORD", "")
    db = os.environ.get("POSTGRES_DB", "yazklinik")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def _masked_dsn(value: str) -> str:
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        netloc = f"{parts.username}:***@{host}" if parts.username else host
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        return "***"


def runtime_config() -> Dict[str, Any]:
    load_config_env()
    primary = _norm(os.environ.get("YAZKLINIK_DB_PRIMARY", "sqlite"))
    mode = _norm(os.environ.get("YAZKLINIK_POSTGRES_MODE", "shadow"))
    dialect = _norm(os.environ.get("YAZKLINIK_DB_DIALECT", "sqlite"))
    postgres_only = _env_bool("YAZKLINIK_POSTGRES_ONLY", False)
    sqlite_path = Path(os.environ.get("YAZKLINIK_DB_PATH") or str(DEFAULT_SQLITE_PATH))
    pg_dsn = _postgres_dsn()
    wants_pg_primary = primary in {"postgres", "postgresql", "pg"} or mode in {
        "primary", "cutover", "postgres_primary"
    }
    if postgres_only:
        wants_pg_primary = True
    return {
        "ok": True,
        "adapter_version": ADAPTER_VERSION,
        "primary": primary,
        "mode": mode,
        "dialect": dialect,
        "postgres_only": postgres_only,
        "enable_postgres": _env_bool("YAZKLINIK_ENABLE_POSTGRES", False),
        "wants_pg_primary": wants_pg_primary,
        "sqlite_path": str(sqlite_path),
        "sqlite_exists": sqlite_path.exists(),
        "postgres_dsn": _masked_dsn(pg_dsn),
    }


def is_postgres_primary_requested() -> bool:
    return bool(runtime_config().get("wants_pg_primary"))


def assert_primary_cutover_allowed(deep: bool = False) -> Dict[str, Any]:
    import YAZKLINIK_POSTGRES_PRIMARY_GUARD as guard

    report = guard.primary_guard(deep=deep)
    if not report.get("ok"):
        blockers = report.get("blockers") or [report.get("guard") or "primary guard failed"]
        raise RuntimeError("PostgreSQL primary cutover blocked: " + "; ".join(map(str, blockers)))
    return report


# The cutover guard is heavyweight: primary_guard() -> readiness_check() ->
# _source_scan() walks the whole source tree and compares SQLite vs PostgreSQL.
# It is a process startup gate, not a per-connection invariant. Runtime opens
# 100+ db_conn() calls per request, so running the guard on every connection
# hangs the app under PG-primary. Cache the allowed result and re-check at most
# once per TTL.
_CUTOVER_GUARD_LOCK = threading.Lock()
_CUTOVER_GUARD_LOCAL = threading.local()
_CUTOVER_GUARD_CACHE = {"ok": False, "checked_at": 0.0}


def _cutover_guard_ttl_seconds() -> float:
    try:
        return float(os.environ.get("YAZKLINIK_POSTGRES_GUARD_CACHE_TTL_SEC", "300") or "300")
    except Exception:
        return 300.0


def reset_cutover_guard_cache() -> None:
    _CUTOVER_GUARD_CACHE["ok"] = False
    _CUTOVER_GUARD_CACHE["checked_at"] = 0.0


def assert_primary_cutover_allowed_cached() -> None:
    """Process-cached cutover guard for the hot runtime-connection path.

    Runs the heavyweight guard at most once per TTL (default 300s, override via
    YAZKLINIK_POSTGRES_GUARD_CACHE_TTL_SEC). Raises the same RuntimeError as
    assert_primary_cutover_allowed when cutover is blocked.
    """
    if getattr(_CUTOVER_GUARD_LOCAL, "in_progress", False):
        return  # re-entrant call from within the guard itself: do not recurse
    ttl = _cutover_guard_ttl_seconds()
    cache = _CUTOVER_GUARD_CACHE
    if cache["ok"] and (time.monotonic() - cache["checked_at"]) < ttl:
        return
    with _CUTOVER_GUARD_LOCK:
        if cache["ok"] and (time.monotonic() - cache["checked_at"]) < ttl:
            return
        _CUTOVER_GUARD_LOCAL.in_progress = True
        try:
            assert_primary_cutover_allowed(deep=False)
            cache["ok"] = True
            cache["checked_at"] = time.monotonic()
        finally:
            _CUTOVER_GUARD_LOCAL.in_progress = False


def assert_sqlite_maintenance_allowed(operation: str = "sqlite-maintenance") -> None:
    if not is_postgres_primary_requested():
        return
    raise RuntimeError(
        f"{operation} is SQLite-only and is blocked while PostgreSQL primary is requested"
    )


def assert_sqlite_runtime_allowed(operation: str = "sqlite-runtime") -> None:
    if not is_postgres_primary_requested():
        return
    raise RuntimeError(
        f"{operation} is SQLite runtime and is blocked while PostgreSQL primary is requested"
    )


def open_sqlite_file_connection(
    path: Any,
    operation: str = "sqlite-file",
    timeout: int = 60,
    isolation_level: Any = _DEFAULT_ISOLATION,
    guard: bool = True,
) -> sqlite3.Connection:
    if guard:
        assert_sqlite_maintenance_allowed(operation)
    kwargs = {"timeout": timeout}
    if isolation_level is not _DEFAULT_ISOLATION:
        kwargs["isolation_level"] = isolation_level
    return sqlite3.connect(str(path), **kwargs)


def open_sqlite_maintenance_connection(
    operation: str = "sqlite-maintenance",
    timeout: int = 60,
    isolation_level: Any = _DEFAULT_ISOLATION,
) -> sqlite3.Connection:
    cfg = runtime_config()
    return open_sqlite_file_connection(
        cfg["sqlite_path"],
        operation=operation,
        timeout=timeout,
        isolation_level=isolation_level,
        guard=True,
    )


def open_sqlite_runtime_connection(
    operation: str = "sqlite-runtime",
    timeout: int = 60,
    isolation_level: Any = _DEFAULT_ISOLATION,
    allow_when_pg_requested: bool = False,
) -> sqlite3.Connection:
    if not allow_when_pg_requested:
        assert_sqlite_runtime_allowed(operation)
    cfg = runtime_config()
    return open_sqlite_file_connection(
        cfg["sqlite_path"],
        operation=operation,
        timeout=timeout,
        isolation_level=isolation_level,
        guard=False,
    )


@contextmanager
def sqlite_maintenance_connection(
    operation: str = "sqlite-maintenance",
    timeout: int = 60,
    isolation_level: Any = _DEFAULT_ISOLATION,
) -> Iterator[sqlite3.Connection]:
    """Open SQLite only for maintenance paths, never as hidden PG-primary fallback."""
    con = open_sqlite_maintenance_connection(
        operation=operation,
        timeout=timeout,
        isolation_level=isolation_level,
    )
    try:
        yield con
    finally:
        con.close()


@contextmanager
def sqlite_runtime_connection(
    operation: str = "sqlite-runtime",
    timeout: int = 60,
    isolation_level: Any = _DEFAULT_ISOLATION,
    allow_when_pg_requested: bool = False,
) -> Iterator[sqlite3.Connection]:
    con = open_sqlite_runtime_connection(
        operation=operation,
        timeout=timeout,
        isolation_level=isolation_level,
        allow_when_pg_requested=allow_when_pg_requested,
    )
    try:
        yield con
    finally:
        con.close()


def postgres_connection():
    load_config_env()
    import psycopg

    con = psycopg.connect(_postgres_dsn(), connect_timeout=8, autocommit=False)
    schema = (
        os.environ.get("YAZKLINIK_POSTGRES_RUNTIME_SCHEMA")
        or os.environ.get("YAZKLINIK_POSTGRES_SHADOW_SCHEMA")
        or os.environ.get("YAZKLINIK_POSTGRES_SCHEMA")
        or os.environ.get("YAZKLINIK_DB_SCHEMA")
        or "public"
    ).strip()
    import re
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", schema):
        con.close()
        raise RuntimeError(f"Unsafe PostgreSQL schema name: {schema!r}")
    with con.cursor() as cur:
        cur.execute(f'SET search_path TO "{schema}", public')
    con.commit()
    return con


class CompatRow(Mapping):
    """Small sqlite3.Row-like wrapper for PostgreSQL result rows."""

    def __init__(self, keys: Any, values: Any):
        self._keys = [str(k) for k in (keys or [])]
        self._values = tuple(values or ())
        self._data = {
            key: self._values[idx]
            for idx, key in enumerate(self._keys)
            if idx < len(self._values)
        }

    def __getitem__(self, key: Any):
        if isinstance(key, int):
            return self._values[key]
        return self._data[str(key)]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def keys(self):
        return self._data.keys()

    def get(self, key: Any, default: Any = None):
        return self._data.get(str(key), default)


class DialectCursor:
    """Cursor wrapper that applies dialect SQL translation before execute."""

    def __init__(self, raw_cursor: Any, dialect: str, row_factory: Any = None):
        self._raw = raw_cursor
        self._dialect = sql_dialect.normalize_dialect(dialect)
        self._row_factory = row_factory
        self._skipped = False
        self._last_translation = None

    def execute(self, sql: str, params: Any = None, **kwargs: Any):
        translated = sql_dialect.translate_sql(
            sql,
            tuple(params or ()),
            dialect=self._dialect,
            conflict_columns=kwargs.pop("conflict_columns", None),
        )
        self._last_translation = translated
        if translated.action == "skip":
            self._skipped = True
            return self
        self._skipped = False
        try:
            # PostgreSQL'de parametresiz sorguyu bos tuple ile calistirmak,
            # LIKE icindeki %...% bolumlerini placeholder gibi yorumlatabilir.
            if translated.params:
                return self._raw.execute(translated.sql, translated.params)
            return self._raw.execute(translated.sql)
        except Exception:
            if self._dialect == "postgresql":
                try:
                    self._raw.connection.rollback()
                except Exception:
                    pass
            raise

    def executemany(self, sql: str, seq_of_params: Any, **kwargs: Any):
        translated = sql_dialect.translate_sql(
            sql,
            (),
            dialect=self._dialect,
            conflict_columns=kwargs.pop("conflict_columns", None),
        )
        self._last_translation = translated
        if translated.action == "skip":
            self._skipped = True
            return self
        self._skipped = False
        try:
            return self._raw.executemany(translated.sql, seq_of_params)
        except Exception:
            if self._dialect == "postgresql":
                try:
                    self._raw.connection.rollback()
                except Exception:
                    pass
            raise

    def fetchone(self):
        if self._skipped:
            return None
        return self._convert_row(self._raw.fetchone())

    def fetchall(self):
        if self._skipped:
            return []
        return [self._convert_row(row) for row in self._raw.fetchall()]

    def _convert_row(self, row: Any):
        if row is None:
            return None
        if self._dialect != "postgresql" or self._row_factory is None:
            return row
        description = getattr(self._raw, "description", None) or []
        keys = [col[0] for col in description]
        if self._row_factory is sqlite3.Row:
            return CompatRow(keys, row)
        try:
            return self._row_factory(self, row)
        except Exception:
            return CompatRow(keys, row)

    @property
    def rowcount(self):
        if self._skipped:
            return 0
        return getattr(self._raw, "rowcount", -1)

    @property
    def lastrowid(self):
        raw_value = getattr(self._raw, "lastrowid", None)
        if self._dialect != "postgresql":
            return raw_value
        if raw_value not in (None, "", 0):
            return raw_value
        try:
            con = getattr(self._raw, "connection", None)
            if con is None:
                return None
            with con.cursor() as cur:
                cur.execute("SELECT lastval()")
                row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else None
        except Exception:
            return None

    def close(self) -> None:
        try:
            self._raw.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def __getattr__(self, name: str):
        return getattr(self._raw, name)


class DialectConnection:
    """Connection wrapper used by PostgreSQL runtime simulation/cutover."""

    def __init__(self, raw_connection: Any, dialect: str):
        object.__setattr__(self, "_raw", raw_connection)
        object.__setattr__(self, "dialect", sql_dialect.normalize_dialect(dialect))
        object.__setattr__(self, "_row_factory", None)

    def cursor(self, *args: Any, **kwargs: Any) -> DialectCursor:
        return DialectCursor(
            self._raw.cursor(*args, **kwargs),
            self.dialect,
            row_factory=self._row_factory,
        )

    def execute(self, sql: str, params: Any = None, **kwargs: Any):
        cur = self.cursor()
        cur.execute(sql, params, **kwargs)
        return cur

    def commit(self):
        return self._raw.commit()

    def rollback(self):
        return self._raw.rollback()

    def close(self):
        return self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def __getattr__(self, name: str):
        return getattr(self._raw, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "row_factory":
            object.__setattr__(self, "_row_factory", value)
            return
        if name in {"_raw", "dialect", "_row_factory"}:
            object.__setattr__(self, name, value)
            return
        setattr(self._raw, name, value)


@contextmanager
def postgres_dialect_connection() -> Iterator[DialectConnection]:
    con = postgres_connection()
    try:
        yield DialectConnection(con, "postgresql")
    finally:
        con.close()


@contextmanager
def runtime_connection(operation: str = "runtime-db") -> Iterator[Any]:
    """Open the active runtime DB connection through the cutover guard.

    Today this yields SQLite because D700 is still in shadow mode. If a future
    cutover sets primary=postgresql, the primary guard must allow it first.
    """
    cfg = runtime_config()
    if cfg.get("wants_pg_primary"):
        if _allow_sqlite_fallback_on_pg_block():
            if not cfg.get("enable_postgres"):
                with sqlite_runtime_connection(
                    operation=f"{operation}-pg-disabled-fallback",
                    allow_when_pg_requested=True,
                ) as sqlite_con:
                    yield sqlite_con
                return
            try:
                con = postgres_connection()
            except Exception:
                with sqlite_runtime_connection(
                    operation=f"{operation}-pg-connect-fallback",
                    allow_when_pg_requested=True,
                ) as sqlite_con:
                    yield sqlite_con
                return
        else:
            assert_primary_cutover_allowed_cached()
            con = postgres_connection()
        try:
            yield DialectConnection(con, "postgresql")
        finally:
            con.close()
        return

    with sqlite_runtime_connection(operation=operation) as con:
        yield con


def agent_connection(label: str = "agent", sqlite_path: Optional[str] = None):
    """Mode-aware DB connection for standalone modules/agents that manage their
    own connection lifecycle: ``con = agent_connection(); ...; con.commit(); con.close()``.

    Non-context-manager counterpart of runtime_connection(). Under PG-primary it
    returns a DialectConnection wrapping PostgreSQL (SQL is dialect-translated, so
    CREATE TABLE / INSERT / SELECT land in PG and agent schemas are created there on
    first use). Otherwise it returns a raw sqlite3 connection to the main DB. The
    caller owns close(). Lets legacy modules drop-in replace
    ``sqlite3.connect(DEFAULT_DB_PATH)`` without restructuring into ``with`` blocks.
    """
    cfg = runtime_config()
    if cfg.get("wants_pg_primary"):
        if _allow_sqlite_fallback_on_pg_block():
            if cfg.get("enable_postgres"):
                try:
                    con = postgres_connection()
                    return DialectConnection(con, "postgresql")
                except Exception:
                    pass
        else:
            assert_primary_cutover_allowed_cached()
            con = postgres_connection()
            return DialectConnection(con, "postgresql")
    path = sqlite_path or os.environ.get("YAZKLINIK_DB_PATH") or str(DEFAULT_SQLITE_PATH)
    return sqlite3.connect(path, timeout=10)


def adapter_status(deep: bool = False) -> Dict[str, Any]:
    cfg = runtime_config()
    wants_pg_primary = bool(cfg.get("wants_pg_primary"))
    out: Dict[str, Any] = {
        "ok": False,
        "adapter_version": ADAPTER_VERSION,
        "config": cfg,
        "checks": [],
        "blockers": [],
    }
    if wants_pg_primary:
        try:
            guard_report = assert_primary_cutover_allowed(deep=deep)
            out["checks"].append({
                "name": "primary_guard",
                "ok": True,
                "guard": guard_report.get("guard"),
                "primary_cutover_ready": (guard_report.get("cutover") or {}).get(
                    "primary_cutover_ready"),
            })
        except Exception as exc:
            out["checks"].append({"name": "primary_guard", "ok": False, "error": str(exc)})
            out["blockers"].append(str(exc))
    else:
        out["checks"].append({
            "name": "primary_guard",
            "ok": True,
            "skipped": True,
            "detail": "sqlite-primary-mode",
        })

    try:
        assert_sqlite_maintenance_allowed("adapter-status-probe")
        out["checks"].append({
            "name": "sqlite_maintenance_guard",
            "ok": not wants_pg_primary,
            "allowed": True,
        })
        if wants_pg_primary:
            out["blockers"].append("SQLite maintenance guard did not block PostgreSQL primary")
    except Exception as exc:
        out["checks"].append({
            "name": "sqlite_maintenance_guard",
            "ok": bool(wants_pg_primary),
            "blocked": str(exc),
        })

    try:
        assert_sqlite_runtime_allowed("adapter-runtime-probe")
        out["checks"].append({
            "name": "sqlite_runtime_guard",
            "ok": not wants_pg_primary,
            "allowed": True,
        })
        if wants_pg_primary:
            out["blockers"].append("SQLite runtime guard did not block PostgreSQL primary")
    except Exception as exc:
        out["checks"].append({
            "name": "sqlite_runtime_guard",
            "ok": bool(wants_pg_primary),
            "blocked": str(exc),
        })

    out["ok"] = all(bool(c.get("ok")) for c in out["checks"])
    return out

