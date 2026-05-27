#!/usr/bin/env python
"""YazKlinik D700 SQLite -> PostgreSQL primary cutover yardimcisi.

Bu arac CANLI klinigi PostgreSQL-primary'ye gecirir (veya geri alir). Calistirma
karari SENINDIR; bakim penceresinde / dusuk kullanimda calistir.

KULLANIM:
  python YAZKLINIK_PG_CUTOVER.py --status        # mevcut mod + PG hazirlik
  python YAZKLINIK_PG_CUTOVER.py --dry-run       # ne degisecek (yazma yok, varsayilan)
  python YAZKLINIK_PG_CUTOVER.py --apply --yes   # CUTOVER: PG'yi tazele + config pg-primary
  python YAZKLINIK_PG_CUTOVER.py --rollback --yes # SQLite'a geri don

ADIMLAR (cutover):
  1) python YAZKLINIK_PG_CUTOVER.py --apply --yes
  2) Server'i yeniden baslat (D500_BASLAT.bat veya D500_ADMIN_WEB_RESTART.bat)
  3) python CODEX_QUICK_CHECK.py   ve   python D500_PRODUCTION_SMOKE.py
  4) Sorun olursa: python YAZKLINIK_PG_CUTOVER.py --rollback --yes  + restart

UYARI: Cutover sonrasi GERCEK hasta yazmalari PostgreSQL'e gider. Rollback
yaparsan o yazmalar SQLite'a yansimaz (yari tek-yonlu). Bu yuzden cutover'i
dusuk kullanimda yap ve hizli karar ver.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.env"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
TYPED_SCHEMA = "yk_pg_typed"
SHADOW_SCHEMA = "yk_sqlite_shadow_current"

CUTOVER_KEYS = {
    "YAZKLINIK_DB_PRIMARY": "postgresql",
    "YAZKLINIK_POSTGRES_MODE": "primary",
    "YAZKLINIK_ENABLE_POSTGRES": "1",
    "YAZKLINIK_DB_DIALECT": "postgresql",
    "YAZKLINIK_POSTGRES_RUNTIME_SCHEMA": TYPED_SCHEMA,
}
ROLLBACK_KEYS = {
    "YAZKLINIK_DB_PRIMARY": "sqlite",
    "YAZKLINIK_POSTGRES_MODE": "shadow",
    "YAZKLINIK_ENABLE_POSTGRES": "0",
    "YAZKLINIK_DB_DIALECT": "sqlite",
    "YAZKLINIK_POSTGRES_RUNTIME_SCHEMA": SHADOW_SCHEMA,
}


def _py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def _read_lines() -> list[str]:
    if not CONFIG.exists():
        return []
    return CONFIG.read_text(encoding="utf-8-sig", errors="replace").splitlines()


def _parsed() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in _read_lines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _set_keys(keys: dict[str, str]) -> None:
    lines = _read_lines()
    seen: set[str] = set()
    for i, line in enumerate(lines):
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in keys:
                lines[i] = f"{k}={keys[k]}"
                seen.add(k)
    for k, v in keys.items():
        if k not in seen:
            lines.append(f"{k}={v}")
    CONFIG.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


def _backup(tag: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = ROOT / f"config.env.bak_{tag}_{ts}"
    shutil.copy2(CONFIG, bak)
    return bak


def _latest_cutover_backup() -> Path | None:
    cands = sorted(ROOT.glob("config.env.bak_cutover_*"))
    return cands[-1] if cands else None


def _pg_precheck() -> dict:
    try:
        os.environ.setdefault("YAZKLINIK_POSTGRES_RUNTIME_SCHEMA", TYPED_SCHEMA)
        import yazklinik_db_adapter as adapter
        con = adapter.postgres_connection()
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema=%s",
                (TYPED_SCHEMA,))
            ntables = int(cur.fetchone()[0])
            npat = None
            if ntables:
                try:
                    cur.execute(f'SELECT count(*) FROM "{TYPED_SCHEMA}".patients')
                    npat = int(cur.fetchone()[0])
                except Exception:
                    npat = None
            cur.execute(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema=%s AND is_identity='YES'", (TYPED_SCHEMA,))
            nident = int(cur.fetchone()[0])
        finally:
            con.close()
        return {"ok": ntables > 0, "schema": TYPED_SCHEMA,
                "tables": ntables, "patients": npat, "identity_cols": nident}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _refresh_typed() -> tuple[bool, str]:
    env = os.environ.copy()
    env["YAZKLINIK_PG_TYPED_SCHEMA"] = "1"
    proc = subprocess.run(
        [_py(), str(ROOT / "YAZKLINIK_POSTGRES_FULL_MIGRATE.py"),
         "--apply", "--yes", "--schema", TYPED_SCHEMA, "--replace"],
        cwd=str(ROOT), env=env, text=True, capture_output=True)
    return proc.returncode == 0, ((proc.stdout or "") + (proc.stderr or ""))[-600:]


def _print_mode(label: str) -> None:
    cur = _parsed()
    print(f"--- {label} ---")
    for k in CUTOVER_KEYS:
        print(f"  {k}={cur.get(k, '(yok)')}")


def cmd_status() -> int:
    _print_mode("Mevcut config")
    pc = _pg_precheck()
    print("--- PostgreSQL hazirlik ---")
    if pc.get("ok"):
        print(f"  PG OK: schema={pc['schema']} tables={pc['tables']} "
              f"patients={pc.get('patients')} identity_cols={pc.get('identity_cols')}")
    else:
        print(f"  PG HAZIR DEGIL: {pc.get('error') or pc}")
    cur = _parsed()
    is_pg = (cur.get("YAZKLINIK_DB_PRIMARY", "").lower() in ("postgres", "postgresql", "pg"))
    print(f"--- Aktif mod: {'PostgreSQL-primary' if is_pg else 'SQLite-primary'} ---")
    return 0


def cmd_dry_run() -> int:
    print("DRY-RUN (yazma yok). --apply --yes ile su degisiklikler yapilacak:")
    cur = _parsed()
    for k, v in CUTOVER_KEYS.items():
        old = cur.get(k, "(yok)")
        print(f"  {k}: {old} -> {v}" + ("  (degismez)" if old == v else ""))
    print("Ayrica: config.env yedeklenir + yk_pg_typed guncel SQLite'tan tazelenir.")
    pc = _pg_precheck()
    print("PG hazirlik:", "OK" if pc.get("ok") else f"HAZIR DEGIL ({pc.get('error') or pc})")
    print("Cutover sonrasi server restart + smoke gerekir (bkz dosya basligi).")
    return 0


def cmd_apply(assume_yes: bool) -> int:
    if not assume_yes:
        print("CUTOVER icin --yes zorunlu. Once --dry-run / --status calistir.", file=sys.stderr)
        return 2
    pc = _pg_precheck()
    if not pc.get("ok"):
        print(f"IPTAL: PostgreSQL/{TYPED_SCHEMA} hazir degil: {pc.get('error') or pc}", file=sys.stderr)
        print("Docker/PG ayakta mi? Once: python YAZKLINIK_POSTGRES_FULL_MIGRATE.py "
              "(YAZKLINIK_PG_TYPED_SCHEMA=1) --apply --yes --schema yk_pg_typed --replace", file=sys.stderr)
        return 1
    bak = _backup("cutover")
    print(f"config.env yedeklendi: {bak.name}")
    print("yk_pg_typed guncel SQLite'tan tazeleniyor...")
    ok, tail = _refresh_typed()
    if not ok:
        print("IPTAL: typed schema tazeleme basarisiz. Config DEGISTIRILMEDI.\n" + tail, file=sys.stderr)
        return 1
    print("  typed refresh OK")
    _set_keys(CUTOVER_KEYS)
    print("config.env -> PostgreSQL-primary yapildi (RUNTIME_SCHEMA=yk_pg_typed).")
    print()
    print("=" * 60)
    print("SIMDI: server'i yeniden baslat (D500_BASLAT.bat / D500_ADMIN_WEB_RESTART.bat)")
    print("SONRA: python CODEX_QUICK_CHECK.py  +  python D500_PRODUCTION_SMOKE.py")
    print("SORUN: python YAZKLINIK_PG_CUTOVER.py --rollback --yes  + restart")
    print("=" * 60)
    return 0


def cmd_rollback(assume_yes: bool) -> int:
    if not assume_yes:
        print("ROLLBACK icin --yes zorunlu.", file=sys.stderr)
        return 2
    _backup("prerollback")
    bak = _latest_cutover_backup()
    if bak and bak.exists():
        shutil.copy2(bak, CONFIG)
        print(f"config.env cutover yedeginden geri yuklendi: {bak.name}")
    else:
        _set_keys(ROLLBACK_KEYS)
        print("Cutover yedegi bulunamadi; SQLite-primary anahtarlari yazildi.")
    print()
    print("=" * 60)
    print("SIMDI: server'i yeniden baslat -> SQLite-primary'ye doner.")
    print("SONRA: python CODEX_QUICK_CHECK.py")
    print("NOT: cutover penceresinde PG'ye yazilan veriler SQLite'ta YOKTUR.")
    print("=" * 60)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="YazKlinik PostgreSQL cutover helper")
    p.add_argument("--status", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--rollback", action="store_true")
    p.add_argument("--yes", action="store_true")
    args = p.parse_args()
    if not CONFIG.exists():
        print(f"config.env bulunamadi: {CONFIG}", file=sys.stderr)
        return 2
    if args.rollback:
        return cmd_rollback(args.yes)
    if args.apply:
        return cmd_apply(args.yes)
    if args.status:
        return cmd_status()
    return cmd_dry_run()


if __name__ == "__main__":
    raise SystemExit(main())

