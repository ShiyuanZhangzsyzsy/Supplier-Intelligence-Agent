"""Shared read-only SQL validation and DuckDB CSV-view helpers.

Centralises logic that was previously duplicated across
``supplier_agent_tools.py`` and ``lmstudio_duckdb_bridge.py``.
"""

from __future__ import annotations

import re

import duckdb

FORBIDDEN_SQL = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "replace",
    "truncate",
    "attach",
    "detach",
    "copy",
    "call",
}

_ALLOWED_PREFIXES = ("select", "with", "show", "describe", "pragma")


def validate_read_only_sql(sql: str, *, allow_multiple: bool = False) -> str:
    """Return a cleaned, validated read-only SQL string or raise ``ValueError``.

    Enforces three independent checks (defence in depth):
    1. statement must start with an allowed read-only keyword,
    2. no forbidden (write/DDL) keywords appear anywhere,
    3. at most one statement unless ``allow_multiple`` is set.
    """
    sql_clean = (sql or "").strip().rstrip(";")
    if not sql_clean:
        raise ValueError("SQL is empty.")

    if not allow_multiple and ";" in sql_clean:
        raise ValueError("Only one SQL statement is allowed.")

    lowered = sql_clean.lower().strip()
    if not lowered.startswith(_ALLOWED_PREFIXES):
        raise ValueError(
            "Only read-only SQL is allowed (SELECT/WITH/SHOW/DESCRIBE/PRAGMA)."
        )

    tokens = set(re.findall(r"[a-zA-Z_]+", lowered))
    hit = sorted(tokens.intersection(FORBIDDEN_SQL))
    if hit:
        raise ValueError(f"Forbidden SQL keywords detected: {', '.join(hit)}")

    return sql_clean


def create_or_replace_csv_view(
    conn: duckdb.DuckDBPyConnection,
    csv_path: str,
    view_name: str = "source_data",
) -> None:
    """Create a DuckDB view over a CSV, trying progressively lenient parsers."""
    escaped_path = csv_path.replace("'", "''")
    candidates = [
        f"SELECT * FROM read_csv_auto('{escaped_path}', HEADER=TRUE)",
        f"SELECT * FROM read_csv_auto('{escaped_path}', HEADER=TRUE, STRICT_MODE=FALSE, IGNORE_ERRORS=TRUE)",
        f"SELECT * FROM read_csv('{escaped_path}', AUTO_DETECT=TRUE, HEADER=TRUE, SAMPLE_SIZE=-1, IGNORE_ERRORS=TRUE, NULL_PADDING=TRUE)",
    ]

    errors: list[str] = []
    for query in candidates:
        try:
            conn.execute(f"CREATE OR REPLACE VIEW {view_name} AS {query}")
            conn.execute(f"SELECT * FROM {view_name} LIMIT 1").fetchall()
            return
        except Exception as exc:  # noqa: BLE001 - collected and re-raised below
            errors.append(str(exc))

    raise RuntimeError(
        "Could not parse CSV with DuckDB direct reader. "
        "Try a cleaner CSV export or specify DuckDB CSV options. "
        f"Last error: {errors[-1] if errors else 'unknown error'}"
    )
