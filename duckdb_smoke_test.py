from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
from resilient_ingestion import load_file_to_duckdb


def normalize_columns(conn: duckdb.DuckDBPyConnection, table_name: str) -> None:
    info = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    for _, original_name, *_ in info:
        normalized = (
            original_name.strip()
            .lower()
            .replace(" ", "_")
            .replace("-", "_")
            .replace("/", "_")
        )
        if normalized != original_name:
            conn.execute(
                f"ALTER TABLE {table_name} RENAME COLUMN \"{original_name}\" TO \"{normalized}\""
            )


def ingest_file(conn: duckdb.DuckDBPyConnection, source: Path, table_name: str) -> int:
    load_file_to_duckdb(str(source), table_name, conn)
    return conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]


def run_smoke_test(db_path: Path, data_path: Path, table_name: str) -> None:
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")

    conn = duckdb.connect(str(db_path))
    try:
        row_count = ingest_file(conn, data_path, table_name)
        print(f"Connected to DuckDB: {db_path}")
        print(f"Loaded {row_count} rows into table: {table_name}")

        print("\nSchema preview:")
        print(conn.execute(f"DESCRIBE {table_name}").fetchdf().head(12).to_string(index=False))

        print("\nSample rows:")
        print(conn.execute(f"SELECT * FROM {table_name} LIMIT 5").fetchdf().to_string(index=False))

        print("\nValidation query:")
        print(conn.execute(f"SELECT COUNT(*) AS total_rows FROM {table_name}").fetchdf().to_string(index=False))
    finally:
        conn.close()
        print("\nConnection closed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DuckDB connection and ingestion smoke test")
    parser.add_argument(
        "--db",
        default="supplier_data.duckdb",
        help="Path to DuckDB database file (default: supplier_data.duckdb)",
    )
    parser.add_argument(
        "--data",
        default="data/NFR_Enterprise_Catalog_1000_Lines.csv",
        help="Path to input catalog file (CSV or Excel)",
    )
    parser.add_argument(
        "--table",
        default="supplier_catalog",
        help="Destination table name (default: supplier_catalog)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_smoke_test(Path(args.db), Path(args.data), args.table)
