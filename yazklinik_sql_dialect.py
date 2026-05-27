#!/usr/bin/env python
"""SQL dialect helpers for YazKlinik SQLite -> PostgreSQL migration."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple


DIALECT_VERSION = "2026.05.19-sql-dialect-adapter"

INSERT_OR_REPLACE_CONFLICTS = {
    "settings": ("key",),
    "phone_numbers": ("patient_key",),
    "dicom_patient_links": ("patient_key", "study_id"),
    "voice_profiles": ("owner_type", "owner_key"),
}


@dataclass(frozen=True)
class TranslatedSQL:
    sql: Optional[str]
    params: Tuple[Any, ...] = ()
    dialect: str = "sqlite"
    action: str = "execute"
    note: str = ""


def normalize_dialect(value: str | None) -> str:
    text = str(value or "sqlite").strip().lower().replace("-", "_")
    if text in {"postgres", "postgresql", "pg"}:
        return "postgresql"
    return "sqlite"


def qmark_to_psycopg(sql: str) -> str:
    """Convert SQLite '?' placeholders to psycopg '%s', preserving quoted '?'."""
    out: List[str] = []
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if in_line_comment:
            out.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            out.append(ch)
            if ch == "*" and nxt == "/":
                out.append(nxt)
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if not in_single and not in_double and ch == "-" and nxt == "-":
            out.extend([ch, nxt])
            in_line_comment = True
            i += 2
            continue
        if not in_single and not in_double and ch == "/" and nxt == "*":
            out.extend([ch, nxt])
            in_block_comment = True
            i += 2
            continue
        if ch == "'" and not in_double:
            out.append(ch)
            if in_single and nxt == "'":
                out.append(nxt)
                i += 2
                continue
            in_single = not in_single
            i += 1
            continue
        if ch == '"' and not in_single:
            out.append(ch)
            if in_double and nxt == '"':
                out.append(nxt)
                i += 2
                continue
            in_double = not in_double
            i += 1
            continue
        out.append("%s" if ch == "?" and not in_single and not in_double else ch)
        i += 1
    return "".join(out)


def escape_psycopg_percent_literals(sql: str) -> str:
    """Escape literal '%' for psycopg while preserving valid placeholders.

    psycopg treats '%' as placeholder prefix. SQLite-origin SQL often contains
    LIKE patterns such as '%muayene%'. Under psycopg these must be written as
    '%%muayene%%' unless they are real placeholders (%s/%b/%t or %%).
    """
    out: List[str] = []
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch != "%":
            out.append(ch)
            i += 1
            continue
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if nxt in {"s", "b", "t", "%"}:
            out.append(ch)
            out.append(nxt)
            i += 2
            continue
        out.append("%%")
        i += 1
    return "".join(out)


def _cols_for_insert(sql: str) -> List[str]:
    match = re.search(
        r"\bINSERT\s+(?:OR\s+\w+\s+)?INTO\s+\w+\s*\(([^)]*)\)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    return [c.strip().strip('"') for c in match.group(1).split(",") if c.strip()]


def _table_for_insert(sql: str) -> str:
    match = re.search(
        r"\bINSERT\s+(?:OR\s+\w+\s+)?INTO\s+([A-Za-z_][A-Za-z0-9_]*)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).strip().lower() if match else ""


def _q(ident: str) -> str:
    """Quote a PostgreSQL identifier so reserved words (e.g. user, order) used as
    column names match their constraints. Safe for ordinary lowercase identifiers."""
    ident = ident.strip().strip('"')
    return '"' + ident.replace('"', '""') + '"'


def insert_or_ignore_to_pg(sql: str) -> Optional[str]:
    if not re.search(r"\bINSERT\s+OR\s+IGNORE\b", sql, flags=re.IGNORECASE):
        return None
    converted = re.sub(r"\bINSERT\s+OR\s+IGNORE\b", "INSERT", sql, flags=re.IGNORECASE)
    if re.search(r"\bON\s+CONFLICT\b", converted, flags=re.IGNORECASE):
        return converted
    return converted.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"


def insert_or_replace_to_pg(sql: str,
                            conflict_columns: Sequence[str] | None = None) -> Optional[str]:
    if not re.search(r"\bINSERT\s+OR\s+REPLACE\b", sql, flags=re.IGNORECASE):
        return None
    columns = _cols_for_insert(sql)
    table_name = _table_for_insert(sql)
    mapped_conflicts = INSERT_OR_REPLACE_CONFLICTS.get(table_name, ())
    if mapped_conflicts and all(col in columns for col in mapped_conflicts):
        conflicts = list(conflict_columns or mapped_conflicts)
    else:
        conflicts = list(conflict_columns or (columns[:1] if columns else []))
    if not conflicts:
        return None
    converted = re.sub(r"\bINSERT\s+OR\s+REPLACE\b", "INSERT", sql,
                       flags=re.IGNORECASE).rstrip().rstrip(";")
    update_cols = [c for c in columns if c not in conflicts]
    target = ", ".join(_q(c) for c in conflicts)
    if update_cols:
        assignments = ", ".join(f"{_q(c)}=EXCLUDED.{_q(c)}" for c in update_cols)
        return f"{converted} ON CONFLICT ({target}) DO UPDATE SET {assignments}"
    return f"{converted} ON CONFLICT ({target}) DO NOTHING"


def sqlite_autoincrement_to_pg(sql: str) -> str:
    return re.sub(
        r"\b((?:\"[^\"]+\")|(?:[A-Za-z_][A-Za-z0-9_]*))\s+"
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        r"\1 INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY",
        sql,
        flags=re.IGNORECASE,
    )


def sqlite_blob_type_to_pg(sql: str) -> str:
    """SQLite BLOB column type -> PostgreSQL bytea.

    Yalniz CREATE/ALTER TABLE icinde uygulanir (orada BLOB bir tiptir).
    SELECT/INSERT'te 'blob' bir kolon adi olabilecegi icin dokunulmaz.
    'type "blob" does not exist' hatasini onler.
    """
    if not re.match(r"^\s*(CREATE\s+TABLE|ALTER\s+TABLE)\b", sql, flags=re.IGNORECASE):
        return sql
    return re.sub(r"\bBLOB\b", "bytea", sql, flags=re.IGNORECASE)


def sqlite_datetime_unixepoch_to_pg(sql: str) -> str:
    """Convert SQLite datetime(value, 'unixepoch') to PG text datetime."""
    return re.sub(
        r"\bdatetime\s*\(\s*([A-Za-z_][A-Za-z0-9_\.]*)\s*,\s*['\"]unixepoch['\"]\s*\)",
        r"to_char(to_timestamp(CAST(\1 AS DOUBLE PRECISION)), 'YYYY-MM-DD HH24:MI:SS')",
        sql,
        flags=re.IGNORECASE,
    )


_COLLATE_NOCASE_RE = re.compile(r"\s+COLLATE\s+NOCASE\b", re.IGNORECASE)


def strip_unsupported_collations(sql: str) -> str:
    """Drop SQLite-only COLLATE NOCASE (PostgreSQL has no such collation).

    Every app usage is in ORDER BY (case-insensitive sort), so dropping it just
    falls back to the default collation. Prevents
    'collation "nocase" for encoding "UTF8" does not exist'.
    """
    return _COLLATE_NOCASE_RE.sub("", sql)


def table_exists_sql(table_name: str, dialect: str = "sqlite") -> TranslatedSQL:
    dialect = normalize_dialect(dialect)
    if dialect == "postgresql":
        return TranslatedSQL(
            "SELECT 1 WHERE to_regclass(%s) IS NOT NULL",
            (table_name,),
            dialect=dialect,
            note="PostgreSQL table existence check",
        )
    return TranslatedSQL(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
        dialect=dialect,
        note="SQLite table existence check",
    )


def sqlite_master_table_check_to_pg(sql: str,
                                    params: Sequence[Any] | None = None
                                    ) -> Optional[TranslatedSQL]:
    text = str(sql or "").strip()
    if "sqlite_master" not in text.lower():
        return None
    if not re.search(r"\btype\s*=\s*['\"]table['\"]", text, flags=re.IGNORECASE):
        return None
    qmark = re.search(r"\bname\s*=\s*\?", text, flags=re.IGNORECASE)
    literal = re.search(r"\bname\s*=\s*['\"]([^'\"]+)['\"]", text, flags=re.IGNORECASE)
    if not qmark and not literal:
        return None
    select_name = bool(re.match(r"^SELECT\s+name\b", text, flags=re.IGNORECASE))
    out_params = tuple(params or ())
    if literal:
        out_params = (literal.group(1),)
    table_name = str(out_params[0] if out_params else "")
    if select_name:
        return TranslatedSQL(
            "SELECT %s AS name WHERE to_regclass(%s) IS NOT NULL",
            (table_name, table_name),
            dialect="postgresql",
            note="sqlite_master table check converted to to_regclass",
        )
    return TranslatedSQL(
        "SELECT 1 WHERE to_regclass(%s) IS NOT NULL",
        (table_name,),
        dialect="postgresql",
        note="sqlite_master table check converted to to_regclass",
    )


def pragma_table_info_to_pg(sql: str) -> Optional[TranslatedSQL]:
    text = str(sql or "").strip().rstrip(";")
    match = re.match(
        r"^PRAGMA\s+table_info\s*\(\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?\s*\)$",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    table_name = match.group(1)
    return TranslatedSQL(
        """
        WITH target_schema AS (
            SELECT n.nspname AS schema_name
            FROM pg_class cls
            JOIN pg_namespace n ON n.oid = cls.relnamespace
            WHERE cls.oid = to_regclass(%s)
            LIMIT 1
        )
        SELECT
            (c.ordinal_position - 1)::int AS cid,
            c.column_name AS name,
            c.data_type AS type,
            CASE WHEN c.is_nullable = 'NO' THEN 1 ELSE 0 END AS notnull,
            c.column_default AS dflt_value,
            CASE WHEN EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON kcu.constraint_schema = tc.constraint_schema
                 AND kcu.constraint_name = tc.constraint_name
                 AND kcu.table_schema = tc.table_schema
                 AND kcu.table_name = tc.table_name
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = c.table_schema
                  AND tc.table_name = c.table_name
                  AND kcu.column_name = c.column_name
            ) THEN 1 ELSE 0 END AS pk
        FROM information_schema.columns c
        JOIN target_schema ts ON ts.schema_name = c.table_schema
        WHERE c.table_name = %s
        ORDER BY c.ordinal_position
        """,
        (table_name, table_name),
        dialect="postgresql",
        note="PRAGMA table_info converted to information_schema.columns",
    )


def _split_top_level_commas(text: str):
    """Split on commas not inside nested parens or single-quoted strings.
    Used to detect the optional GROUP_CONCAT separator argument."""
    parts = []
    depth = 0
    in_quote = False
    buf = []
    for ch in text:
        if ch == "'":
            in_quote = not in_quote
            buf.append(ch)
        elif not in_quote and ch == "(":
            depth += 1
            buf.append(ch)
        elif not in_quote and ch == ")":
            depth -= 1
            buf.append(ch)
        elif not in_quote and ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def group_concat_to_string_agg(sql: str) -> str:
    """SQLite GROUP_CONCAT(expr[, sep]) -> PostgreSQL string_agg(expr::text, sep).

    Paren/quote-aware so nested calls like GROUP_CONCAT(DISTINCT NULLIF(TRIM(x),''))
    translate correctly. Missing separator defaults to ',' (SQLite default). expr
    is cast to text so PG accepts non-text columns like SQLite's implicit stringify.
    """
    lowered = sql.lower()
    needle = "group_concat("
    idx = lowered.find(needle)
    if idx == -1:
        return sql
    out = []
    i = 0
    while idx != -1:
        out.append(sql[i:idx])
        open_paren = idx + len("group_concat")
        depth = 0
        in_quote = False
        j = open_paren
        while j < len(sql):
            ch = sql[j]
            if ch == "'":
                in_quote = not in_quote
            elif not in_quote and ch == "(":
                depth += 1
            elif not in_quote and ch == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= len(sql):
            out.append(sql[idx:])
            return "".join(out)
        inner = sql[open_paren + 1:j]
        parts = _split_top_level_commas(inner)
        if len(parts) >= 2:
            expr = parts[0].strip()
            sep = parts[1].strip()
        else:
            expr = inner.strip()
            sep = "','"
        m = re.match(r"(?is)^(distinct\s+)?(.*)$", expr)
        distinct = "DISTINCT " if (m and m.group(1)) else ""
        body = (m.group(2).strip() if m else expr) or expr
        out.append("string_agg(%s(%s)::text, %s)" % (distinct, body, sep))
        i = j + 1
        idx = lowered.find(needle, i)
    out.append(sql[i:])
    return "".join(out)


_DATETIME_NOW_RE = re.compile(r"datetime\(\s*'now'\s*\)", re.IGNORECASE)
_DATE_NOW_RE = re.compile(r"(?<![\w.])date\(\s*'now'\s*\)", re.IGNORECASE)


def sqlite_now_to_pg(sql: str) -> str:
    """SQLite datetime('now')/date('now') -> PostgreSQL. Produces UTC text in the
    same 'YYYY-MM-DD HH:MM:SS' / 'YYYY-MM-DD' shape SQLite yields, so TEXT columns
    stay format-compatible. (Modifier forms like datetime('now','-1 day') are left
    untouched and should be handled at the call site.)"""
    sql = _DATETIME_NOW_RE.sub(
        "to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')", sql)
    sql = _DATE_NOW_RE.sub(
        "to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD')", sql)
    return sql


def translate_sql(sql: str,
                  params: Sequence[Any] | None = None,
                  dialect: str = "sqlite",
                  conflict_columns: Sequence[str] | None = None) -> TranslatedSQL:
    dialect = normalize_dialect(dialect)
    param_tuple = tuple(params or ())
    if dialect != "postgresql":
        return TranslatedSQL(sql, param_tuple, dialect=dialect)
    stripped = str(sql or "").strip()
    pragma_table_info = pragma_table_info_to_pg(stripped)
    if pragma_table_info is not None:
        return pragma_table_info
    if re.match(r"^PRAGMA\b", stripped, flags=re.IGNORECASE):
        return TranslatedSQL(
            None,
            (),
            dialect=dialect,
            action="skip",
            note="SQLite PRAGMA skipped under PostgreSQL",
        )
    if re.match(r"^CREATE\s+TRIGGER\b", stripped, flags=re.IGNORECASE):
        # SQLite trigger bodies (BEGIN..END, IF NOT EXISTS) are incompatible with
        # PostgreSQL (which needs a plpgsql function). Skip under PG; the equivalent
        # logic is handled in application code.
        return TranslatedSQL(
            None,
            (),
            dialect=dialect,
            action="skip",
            note="SQLite CREATE TRIGGER skipped under PostgreSQL",
        )
    table_check = sqlite_master_table_check_to_pg(stripped, param_tuple)
    if table_check is not None:
        return table_check
    converted = insert_or_ignore_to_pg(stripped)
    if converted is None:
        converted = insert_or_replace_to_pg(stripped, conflict_columns=conflict_columns)
    if converted is None:
        converted = stripped
    converted = sqlite_autoincrement_to_pg(converted)
    converted = sqlite_blob_type_to_pg(converted)
    converted = sqlite_datetime_unixepoch_to_pg(converted)
    converted = sqlite_now_to_pg(converted)
    converted = strip_unsupported_collations(converted)
    converted = group_concat_to_string_agg(converted)
    converted = qmark_to_psycopg(converted)
    converted = escape_psycopg_percent_literals(converted)
    return TranslatedSQL(converted, param_tuple, dialect=dialect)
