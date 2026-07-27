from __future__ import annotations

import os
from pathlib import Path

import duckdb
from crewai.tools import tool

from sql_safety import create_or_replace_csv_view, validate_read_only_sql


def _get_runtime_settings() -> tuple[str, str, str | None]:
    db_path = os.getenv("SUPPLIER_DB_PATH", "supplier_data.duckdb")
    table_name = os.getenv("SUPPLIER_TABLE", "supplier_catalog")
    source_csv = os.getenv("SUPPLIER_SOURCE_CSV") or None
    return db_path, table_name, source_csv


def _connect_for_query(source_csv: str | None, db_path: str) -> duckdb.DuckDBPyConnection:
    db_file = Path(db_path)
    if source_csv:
        return duckdb.connect(":memory:")
    if db_file.exists():
        return duckdb.connect(str(db_file), read_only=True)
    return duckdb.connect(str(db_file))


def _prepare_source(conn: duckdb.DuckDBPyConnection, table_name: str, source_csv: str | None) -> str:
    if source_csv:
        csv_path = Path(source_csv)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV source file not found: {csv_path}")
        create_or_replace_csv_view(conn, str(csv_path), table_name)
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
    sql = validate_read_only_sql(query)

    conn = _connect_for_query(source_csv, db_path)
    try:
        source_name = _prepare_source(conn, table_name, source_csv)
        df = conn.execute(sql).fetchdf()
        if df.empty:
            return "(no rows)"
        return df.to_markdown(index=False)
    except Exception as exc:  # noqa: BLE001 - surfaced to the agent as text
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
