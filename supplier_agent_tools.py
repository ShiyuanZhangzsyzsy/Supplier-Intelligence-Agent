from __future__ import annotations

import os
import re
from pathlib import Path

import duckdb
from crewai.tools import tool

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


def _validate_read_only_sql(sql: str) -> str:
    sql_clean = (sql or "").strip().rstrip(";")
    if not sql_clean:
        raise ValueError("SQL is empty.")

    lowered = sql_clean.lower().strip()
    if not lowered.startswith(("select", "with", "show", "describe", "pragma")):
        raise ValueError("Only read-only SQL is allowed (SELECT/WITH/SHOW/DESCRIBE/PRAGMA).")

    tokens = set(re.findall(r"[a-zA-Z_]+", lowered))
    hit = sorted(tokens.intersection(FORBIDDEN_SQL))
    if hit:
        raise ValueError(f"Forbidden SQL keywords detected: {', '.join(hit)}")

    return sql_clean


def _get_runtime_settings() -> tuple[str, str, str | None]:
    db_path = os.getenv("SUPPLIER_DB_PATH", "supplier_data.duckdb")
    table_name = os.getenv("SUPPLIER_TABLE", "supplier_catalog")
    source_csv = os.getenv("SUPPLIER_SOURCE_CSV")
    return db_path, table_name, source_csv


def _connect_for_query(source_csv: str | None, db_path: str) -> duckdb.DuckDBPyConnection:
    db_file = Path(db_path)
    if source_csv:
        return duckdb.connect(":memory:")
    if db_file.exists():
        return duckdb.connect(str(db_file), read_only=True)
    return duckdb.connect(str(db_file))


def _create_or_replace_csv_view(conn: duckdb.DuckDBPyConnection, csv_path: str, view_name: str) -> None:
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
        except Exception as exc:
            errors.append(str(exc))

    raise RuntimeError(
        "Could not parse CSV with DuckDB direct reader. "
        f"Last error: {errors[-1] if errors else 'unknown error'}"
    )


def _prepare_source(conn: duckdb.DuckDBPyConnection, table_name: str, source_csv: str | None) -> str:
    if source_csv:
        csv_path = Path(source_csv)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV source file not found: {csv_path}")
        _create_or_replace_csv_view(conn, str(csv_path), table_name)
    return table_name


def get_schema_impl() -> str:
    db_path, table_name, source_csv = _get_runtime_settings()
    conn = _connect_for_query(source_csv, db_path)
    try:
        source_name = _prepare_source(conn, table_name, source_csv)
        df = conn.execute(f"DESCRIBE {source_name}").fetchdf()
        return df.to_markdown(index=False)
    finally:
        conn.close()


def execute_sql_impl(query: str) -> str:
    db_path, table_name, source_csv = _get_runtime_settings()
    sql = _validate_read_only_sql(query)

    conn = _connect_for_query(source_csv, db_path)
    try:
        source_name = _prepare_source(conn, table_name, source_csv)
        if source_name != table_name:
            pass
        df = conn.execute(sql).fetchdf()
        if df.empty:
            return "(no rows)"
        return df.to_markdown(index=False)
    except Exception as exc:
        return f"Error: {exc}"
    finally:
        conn.close()


@tool("get_schema")
def get_schema() -> str:
    """Get supplier data schema in markdown format for SQL planning."""
    return get_schema_impl()


@tool("execute_sql")
def execute_sql(query: str) -> str:
    """Execute a read-only SQL query and return results in markdown format."""
    return execute_sql_impl(query)
