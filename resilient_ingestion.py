from __future__ import annotations

from pathlib import Path

import duckdb


def _looks_like_excel(file_path: Path) -> bool:
    try:
        with file_path.open("rb") as handle:
            magic = handle.read(4)
        return magic == b"PK\x03\x04"
    except OSError:
        return False


def _normalize_column_name(name: str) -> str:
    return (
        name.strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


def load_file_to_duckdb(
    filepath: str,
    table_name: str,
    conn: duckdb.DuckDBPyConnection,
) -> list[str]:
    source_path = Path(filepath)
    if not source_path.exists():
        raise FileNotFoundError(f"Data file not found: {source_path}")

    is_excel = _looks_like_excel(source_path)

    if is_excel:
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError(
                "Excel-like input detected but pandas/openpyxl is missing. "
                "Install with: pip install pandas openpyxl"
            ) from exc

        df = pd.read_excel(source_path, engine="openpyxl")
    else:
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError(
                "CSV input detected but pandas is missing. Install with: pip install pandas"
            ) from exc

        parse_errors: list[str] = []
        df = None
        for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                df = pd.read_csv(source_path, encoding=encoding)
                break
            except Exception as exc:
                parse_errors.append(f"{encoding}: {exc}")

        if df is None:
            raise RuntimeError(
                f"Could not parse file {source_path}. Attempts: {' | '.join(parse_errors)}"
            )

    df.columns = [_normalize_column_name(str(col)) for col in df.columns]

    conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")

    return [str(col) for col in df.columns]
