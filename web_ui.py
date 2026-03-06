from __future__ import annotations

import os
from pathlib import Path

import duckdb
import gradio as gr
from dotenv import load_dotenv

from resilient_ingestion import load_file_to_duckdb
from supplier_agents import run_supplier_agents


load_dotenv()


def _resolve_uploaded_file(file_input: str | None) -> str | None:
    if not file_input:
        return None
    return str(Path(file_input))


def ask_supplier_agent(
    message: str,
    history,
    mode: str,
    file_path: str | None,
    db_path: str,
    table_name: str,
    base_url: str,
    model: str,
    api_key: str,
):
    question = (message or "").strip()
    if not question:
        return "Please enter a question."

    db_path = (db_path or "").strip() or "supplier_data.duckdb"
    table_name = (table_name or "").strip() or "supplier_catalog"
    base_url = (base_url or "").strip() or (os.getenv("LMSTUDIO_BASE_URL") or os.getenv("PARSING_AGENT_BASE_URL") or "http://127.0.0.1:1234")
    model = (model or "").strip() or (os.getenv("LMSTUDIO_MODEL") or "local-model")
    api_key = (api_key or "").strip() or (os.getenv("LMSTUDIO_API_KEY") or os.getenv("PARSING_AGENT_API_KEY") or "lm-studio")

    source_file = _resolve_uploaded_file(file_path)

    try:
        if mode == "Ingest file into DuckDB table":
            if not source_file:
                return "Please provide a file path in ingest mode."
            with duckdb.connect(db_path) as conn:
                cols = load_file_to_duckdb(source_file, table_name, conn)
            os.environ["SUPPLIER_SOURCE_CSV"] = ""
            preface = (
                f"Loaded '{Path(source_file).name}' into table '{table_name}' "
                f"with {len(cols)} columns.\n\n"
            )
            result = run_supplier_agents(
                question=question,
                base_url=base_url,
                model=model,
                api_key=api_key,
                db_path=db_path,
                table=table_name,
                source_csv=None,
            )
            return preface + result

        if mode == "Query file directly (no ingestion)":
            if not source_file:
                return "Please provide a file path in direct-file mode."
            result = run_supplier_agents(
                question=question,
                base_url=base_url,
                model=model,
                api_key=api_key,
                db_path=db_path,
                table=table_name,
                source_csv=source_file,
            )
            return result

        return "Unknown mode selected."
    except Exception as exc:
        return f"Error: {exc}"


def build_demo() -> gr.Blocks:
    default_base_url = os.getenv("LMSTUDIO_BASE_URL") or os.getenv("PARSING_AGENT_BASE_URL") or "http://127.0.0.1:1234"
    default_model = os.getenv("LMSTUDIO_MODEL") or "local-model"
    default_api_key = os.getenv("LMSTUDIO_API_KEY") or os.getenv("PARSING_AGENT_API_KEY") or "lm-studio"

    with gr.Blocks(title="Supplier Intelligence Agent") as demo:
        gr.Markdown("# Supplier Intelligence Agent")
        gr.Markdown("Ask procurement questions using LM Studio + DuckDB.")

        gr.ChatInterface(
            fn=ask_supplier_agent,
            additional_inputs=[
                gr.Radio(
                    choices=["Query file directly (no ingestion)", "Ingest file into DuckDB table"],
                    value="Query file directly (no ingestion)",
                    label="Data Mode",
                ),
                gr.Textbox(
                    value="data/Coupa_PO_History_Last_5_Years_With_Invoices-1.csv",
                    label="Data File Path (.csv or disguised .xlsx)",
                ),
                gr.Textbox(value="supplier_data.duckdb", label="DuckDB Path"),
                gr.Textbox(value="supplier_catalog", label="Table/View Name"),
                gr.Textbox(value=default_base_url, label="LM Studio Base URL"),
                gr.Textbox(value=default_model, label="Model Name"),
                gr.Textbox(value=default_api_key, label="API Key", type="password"),
            ],
        )
    return demo


if __name__ == "__main__":
    app = build_demo()
    app.launch(server_name="127.0.0.1", server_port=7860)
