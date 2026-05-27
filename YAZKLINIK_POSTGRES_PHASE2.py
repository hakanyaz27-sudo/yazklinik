#!/usr/bin/env python
"""PostgreSQL Phase 2 bootstrapping utility for YazKlinik D700.

Kullanim:
  python YAZKLINIK_POSTGRES_PHASE2.py --dry-run
  python YAZKLINIK_POSTGRES_PHASE2.py --apply --init-schema --yes
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yazklinik_postgres_agent as pg


ROOT = Path(__file__).resolve().parent


def _reexec_with_project_venv() -> None:
    if os.environ.get("YAZKLINIK_PG_PHASE2_NO_REEXEC") == "1":
        return
    if os.name != "nt":
        return
    venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not venv_py.exists():
        return
    try:
        current = Path(sys.executable).resolve()
        target = venv_py.resolve()
    except Exception:
        return
    if current == target:
        return
    os.environ["YAZKLINIK_PG_PHASE2_NO_REEXEC"] = "1"
    os.execv(str(target), [str(target), str(Path(__file__).resolve()), *sys.argv[1:]])


def parse_args():
    p = argparse.ArgumentParser(description="YazKlinik PostgreSQL phase2")
    p.add_argument("--sqlite", default=None, help="Kaynak SQLite yolu")
    p.add_argument("--tables", nargs="*", default=["patients", "visits"], help="Migrate edilecek tablolar")
    p.add_argument("--dry-run", action="store_true", help="Default: sadece rapor (yazma yok)")
    p.add_argument("--apply", action="store_true", help="GerÃ§ek migrate islemi yapsin")
    p.add_argument("--init-schema", action="store_true", help="Gerekirse PG tablolarini olustur")
    p.add_argument("--compare", action="store_true", help="Yaz-kaynak ve PG satir sayisi karsilastirmasi")
    p.add_argument("--health", action="store_true", help="Sadece PG health kontrolu")
    p.add_argument("--yes", action="store_true", help="--apply icin onay")
    return p.parse_args()


def main():
    _reexec_with_project_venv()
    args = parse_args()

    if args.dry_run and args.apply:
        raise SystemExit("dry-run ve apply birlikte kullanilamaz.")
    if args.health:
        print(json.dumps(pg.health_check(), ensure_ascii=False, indent=2))
        return

    if args.compare:
        print(json.dumps(pg.compare_counts(sqlite_path=args.sqlite, tables=args.tables),
                        ensure_ascii=False, indent=2))
        return

    if args.apply and not args.yes:
        raise SystemExit("GerÃ§ek migrate icin --yes zorunlu (veri korunur).")

    sqlite_path = args.sqlite or os.environ.get("YAZKLINIK_DB_PATH") or str(
        ROOT / "local_db" / "yazklinik_v68.sqlite3"
    )
    if not Path(sqlite_path).exists():
        raise SystemExit(f"SQLite bulunamadi: {sqlite_path}")

    if args.apply:
        print("MIGRATE START (AYNI ZAMAN KAYIT GÃœVENLIGI): DRY_RUN=false")
        result = pg.migrate_from_sqlite(sqlite_path=sqlite_path, tables=args.tables,
                                       dry_run=False, init_schema_if_missing=args.init_schema)
    else:
        print("DRY RUN: sadece rapor aliniyor, yazma yok.")
        result = pg.migrate_from_sqlite(sqlite_path=sqlite_path, tables=args.tables,
                                       dry_run=True, init_schema_if_missing=False)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

