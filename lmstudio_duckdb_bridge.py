from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import duckdb
from openai import OpenAI

from sql_safety import (
    create_or_replace_csv_view,
    validate_read_only_sql as _shared_validate_read_only_sql,
)


class LMStudioClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
    ):
        resolved_base_url = (
            base_url
            or os.getenv("LMSTUDIO_BASE_URL")
            or os.getenv("PARSING_AGENT_BASE_URL")
            or "http://127.0.0.1:1234"
        ).rstrip("/")
        if not resolved_base_url.endswith("/v1"):
            resolved_base_url = f"{resolved_base_url}/v1"

        self.base_url = resolved_base_url
        self.model = (
            model
            or os.getenv("LMSTUDIO_MODEL")
            or os.getenv("PARSING_AGENT_MODEL")
            or "local-model"
        )
        self.api_key = (
            api_key
            or os.getenv("LMSTUDIO_API_KEY")
            or os.getenv("PARSING_AGENT_API_KEY")
            or "lm-studio"
        )

        if timeout_seconds is None:
            try:
                timeout_seconds = float(os.getenv("LMSTUDIO_TIMEOUT_SECONDS", "90"))
            except Exception:
                timeout_seconds = 90.0
        self.timeout_seconds = timeout_seconds
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                timeout=self.timeout_seconds,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to call LM Studio at {self.base_url}. "
                "Confirm LM Studio local server is running and model is loaded."
            ) from exc


def get_schema(conn: duckdb.DuckDBPyConnection, table: str) -> str:
    df = conn.execute(f"DESCRIBE {table}").fetchdf()
    return df.to_markdown(index=False)


def extract_sql(text: str) -> str:
    code_block = re.findall(r"```(?:sql)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if code_block:
        return code_block[0].strip().rstrip(";")
    return text.strip().rstrip(";")


def validate_read_only_sql(sql: str) -> None:
    """Validate model-generated SQL, delegating to the shared safety module."""
    _shared_validate_read_only_sql(sql)


def question_to_sql(
    lm_client: LMStudioClient,
    question: str,
    schema_markdown: str,
    table_name: str,
) -> str:
    system_prompt = (
        "You are a senior SQL analyst. Return ONLY one DuckDB-compatible read-only SQL query "
        "for the user question. Use only the provided table and columns. "
        "No explanation, no markdown, no backticks."
    )
    user_prompt = (
        f"Table: {table_name}\n"
        f"Schema:\n{schema_markdown}\n\n"
        f"Question: {question}\n\n"
        "Constraints:\n"
        "- Use only read-only SQL.\n"
        "- Prefer explicit column names.\n"
        "- Add LIMIT 20 when returning detailed rows unless user asks for all rows."
    )

    raw = lm_client.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    sql = extract_sql(raw)
    validate_read_only_sql(sql)
    return sql


def explain_results(
    lm_client: LMStudioClient,
    question: str,
    sql: str,
    result_markdown: str,
) -> str:
    system_prompt = (
        "You are a procurement analytics assistant. Summarize SQL results clearly and briefly. "
        "Do not invent values that are not in the result table."
    )
    user_prompt = (
        f"Question: {question}\n\n"
        f"SQL used:\n{sql}\n\n"
        f"Result table:\n{result_markdown}\n\n"
        "Provide: 1) direct answer 2) one short insight."
    )
    return lm_client.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )


def ask_once(
    conn: duckdb.DuckDBPyConnection,
    lm_client: LMStudioClient,
    table_name: str,
    question: str,
    max_rows: int,
    csv_source: str | None = None,
) -> None:
    if csv_source:
        create_or_replace_csv_view(conn, csv_source, view_name=table_name)

    schema = get_schema(conn, table_name)
    sql = question_to_sql(lm_client, question, schema, table_name)
    result_df = conn.execute(sql).fetchdf().head(max_rows)

    print("\nGenerated SQL:")
    print(sql)

    print("\nResult:")
    if result_df.empty:
        print("(no rows)")
        result_markdown = "(no rows)"
    else:
        print(result_df.to_string(index=False))
        result_markdown = result_df.to_markdown(index=False)

    summary = explain_results(lm_client, question, sql, result_markdown)
    print("\nModel summary:")
    print(summary)


def interactive_loop(
    conn: duckdb.DuckDBPyConnection,
    lm_client: LMStudioClient,
    table_name: str,
    max_rows: int,
    csv_source: str | None = None,
) -> None:
    print("LM Studio + DuckDB bridge ready. Type a question, or :quit to exit.")
    while True:
        try:
            question = input("ask> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not question:
            continue
        if question in {":quit", ":exit"}:
            print("Exiting.")
            break

        try:
            ask_once(
                conn=conn,
                lm_client=lm_client,
                table_name=table_name,
                question=question,
                max_rows=max_rows,
                csv_source=csv_source,
            )
        except Exception as exc:
            print(f"Error: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LM Studio to DuckDB local analytics bridge")
    parser.add_argument(
        "--db",
        default="supplier_data.duckdb",
        help="DuckDB file path (optional when --source-csv is provided)",
    )
    parser.add_argument("--table", default="supplier_catalog", help="Table to query")
    parser.add_argument(
        "--base-url",
        default=None,
        help="LM Studio server base URL (defaults from env or http://127.0.0.1:1234)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name loaded in LM Studio (defaults from env)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key for LM Studio OpenAI-compatible endpoint (default: lm-studio)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=None,
        help="Request timeout for LM calls (seconds)",
    )
    parser.add_argument(
        "--source-csv",
        default=None,
        help="Optional CSV path. When provided, queries run against read_csv_auto(...) view without loading into DB table.",
    )
    parser.add_argument("--question", help="Ask one question and exit")
    parser.add_argument("--max-rows", type=int, default=20, help="Max rows to display")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    csv_source = args.source_csv
    if csv_source is not None:
        csv_path = Path(csv_source)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV source file not found: {csv_path}")
        csv_source = str(csv_path)

    db_path = Path(args.db) if args.db else None
    if db_path and db_path.exists():
        conn = duckdb.connect(str(db_path), read_only=True)
    elif csv_source:
        conn = duckdb.connect(":memory:")
    else:
        raise FileNotFoundError(
            f"DuckDB file not found: {db_path}. Provide an existing --db, or use --source-csv."
        )

    lm_client = LMStudioClient(
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
        timeout_seconds=args.timeout_seconds,
    )

    try:
        if args.question:
            ask_once(
                conn=conn,
                lm_client=lm_client,
                table_name=args.table,
                question=args.question,
                max_rows=args.max_rows,
                csv_source=csv_source,
            )
        else:
            interactive_loop(
                conn=conn,
                lm_client=lm_client,
                table_name=args.table,
                max_rows=args.max_rows,
                csv_source=csv_source,
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
