from __future__ import annotations

import argparse
import duckdb


def print_df(df, max_rows: int = 30) -> None:
    if df is None:
        return
    if hasattr(df, "head"):
        print(df.head(max_rows).to_string(index=False))
    else:
        print(df)


def run_query(conn: duckdb.DuckDBPyConnection, sql: str, max_rows: int) -> None:
    sql_clean = sql.strip().rstrip(";")
    if not sql_clean:
        return

    try:
        result = conn.execute(sql_clean)
        lowered = sql_clean.lower()
        if lowered.startswith(("select", "with", "show", "describe", "pragma")):
            print_df(result.fetchdf(), max_rows=max_rows)
        else:
            print("Query executed successfully.")
    except Exception as exc:
        print(f"Error: {exc}")


def print_help() -> None:
    print(
        """
Commands:
  :help                     Show this help
  :tables                   List all tables
  :schema <table>           Describe table columns
  :sample <table> [n]       Preview n rows (default 10)
  :quit / :exit             Exit

Or type any SQL statement directly.
Examples:
  SELECT COUNT(*) FROM supplier_catalog;
  SELECT supplier_name, AVG(unit_price)
  FROM supplier_catalog
  GROUP BY supplier_name
  ORDER BY 2 DESC
  LIMIT 10;
""".strip()
    )


def interactive_loop(conn: duckdb.DuckDBPyConnection, max_rows: int) -> None:
    print("DuckDB CLI connected. Type :help for commands.")

    while True:
        try:
            user_input = input("duckdb> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_input:
            continue

        if user_input in {":quit", ":exit"}:
            print("Exiting.")
            break

        if user_input == ":help":
            print_help()
            continue

        if user_input == ":tables":
            run_query(conn, "SHOW TABLES", max_rows=max_rows)
            continue

        if user_input.startswith(":schema"):
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                print("Usage: :schema <table>")
            else:
                run_query(conn, f"DESCRIBE {parts[1]}", max_rows=max_rows)
            continue

        if user_input.startswith(":sample"):
            parts = user_input.split()
            if len(parts) < 2:
                print("Usage: :sample <table> [n]")
            else:
                table_name = parts[1]
                limit = 10
                if len(parts) >= 3:
                    try:
                        limit = int(parts[2])
                    except ValueError:
                        print("n must be an integer")
                        continue
                run_query(conn, f"SELECT * FROM {table_name} LIMIT {limit}", max_rows=max_rows)
            continue

        run_query(conn, user_input, max_rows=max_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple DuckDB interactive query CLI")
    parser.add_argument("--db", default="supplier_data.duckdb", help="Path to DuckDB file")
    parser.add_argument("--query", help="Run one SQL query and exit")
    parser.add_argument("--max-rows", type=int, default=30, help="Max rows to print")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    conn = duckdb.connect(args.db)
    try:
        if args.query:
            run_query(conn, args.query, max_rows=args.max_rows)
        else:
            interactive_loop(conn, max_rows=args.max_rows)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
