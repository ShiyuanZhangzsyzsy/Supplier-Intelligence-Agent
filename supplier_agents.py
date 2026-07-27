from __future__ import annotations

import argparse
import os
from typing import Any

from crewai import Agent, Crew, LLM, Process, Task
from dotenv import load_dotenv

from supplier_agent_tools import execute_sql, get_schema


load_dotenv()


def _normalize_base_url(base_url: str) -> str:
    trimmed = base_url.rstrip("/")
    if not trimmed.endswith("/v1"):
        trimmed = f"{trimmed}/v1"
    return trimmed


def _resolve_lmstudio_config(
    base_url: str | None,
    model: str | None,
    api_key: str | None,
) -> tuple[str, str, str]:
    resolved_base_url = _normalize_base_url(
        base_url
        or os.getenv("LMSTUDIO_BASE_URL")
        or os.getenv("PARSING_AGENT_BASE_URL")
        or "http://127.0.0.1:1234"
    )
    resolved_model = (
        model
        or os.getenv("LMSTUDIO_MODEL")
        or "local-model"
    )
    resolved_api_key = (
        api_key
        or os.getenv("LMSTUDIO_API_KEY")
        or os.getenv("PARSING_AGENT_API_KEY")
        or "lm-studio"
    )

    return resolved_base_url, resolved_model, resolved_api_key


def _raise_friendly_lmstudio_error(exc: Exception, base_url: str, model: str) -> None:
    text = str(exc)

    if "OPENAI_API_KEY is required" in text:
        raise RuntimeError(
            "LM credentials are missing. Set LM Studio API key in UI or .env "
            "(LMSTUDIO_API_KEY or PARSING_AGENT_API_KEY)."
        ) from exc

    if "Failed to load model" in text and "System resources observer shutdown requested" in text:
        raise RuntimeError(
            f"LM Studio could not load model '{model}' due to local resource limits. "
            "Open LM Studio and load a smaller quantized model, or free RAM/VRAM, then retry."
        ) from exc

    if "No models loaded" in text:
        raise RuntimeError(
            "No model is loaded in LM Studio. Open LM Studio Developer page and load a chat model, "
            "or run 'lms load <model>'."
        ) from exc

    if "Connection error" in text or "WinError 10061" in text:
        raise RuntimeError(
            f"Cannot connect to LM Studio at {base_url}. Start LM Studio local server and verify the URL."
        ) from exc

    raise RuntimeError(f"LLM request failed: {text}") from exc


def _build_llm(base_url: str | None, model: str | None, api_key: str | None) -> LLM:
    resolved_base_url, resolved_model, resolved_api_key = _resolve_lmstudio_config(
        base_url=base_url,
        model=model,
        api_key=api_key,
    )

    os.environ["OPENAI_API_KEY"] = resolved_api_key
    os.environ["OPENAI_BASE_URL"] = resolved_base_url
    os.environ["OPENAI_API_BASE"] = resolved_base_url
    os.environ["OPENAI_MODEL_NAME"] = resolved_model

    return LLM(
        model=resolved_model,
        provider="openai",
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        api_base=resolved_base_url,
        temperature=0,
    )


def run_supplier_agents(
    question: str,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    db_path: str = "supplier_data.duckdb",
    table: str = "supplier_catalog",
    source_csv: str | None = None,
) -> str:
    os.environ["SUPPLIER_DB_PATH"] = db_path
    os.environ["SUPPLIER_TABLE"] = table
    if source_csv:
        os.environ["SUPPLIER_SOURCE_CSV"] = source_csv
    elif "SUPPLIER_SOURCE_CSV" in os.environ:
        del os.environ["SUPPLIER_SOURCE_CSV"]

    resolved_base_url, resolved_model, resolved_api_key = _resolve_lmstudio_config(
        base_url=base_url,
        model=model,
        api_key=api_key,
    )

    llm = _build_llm(
        base_url=resolved_base_url,
        model=resolved_model,
        api_key=resolved_api_key,
    )

    route = _classify_route(llm, question)

    try:
        if route == "SQL":
            return _run_sql_path(llm, question)
        return _run_insight_path(llm, question)
    except Exception as exc:
        _raise_friendly_lmstudio_error(exc, base_url=resolved_base_url, model=resolved_model)
        raise


def _classify_route(llm: LLM, question: str) -> str:
    """Classify a question as ``SQL`` or ``INSIGHT`` and branch on the result.

    Runs the router as a one-task crew, then normalises its free-text answer to
    one of the two supported routes. Anything that isn't clearly ``INSIGHT``
    falls back to ``SQL``, since the dataset is the safer default for
    procurement questions.
    """
    router_agent = Agent(
        role="Query Router",
        goal="Classify if the user query needs SQL analytics from supplier data.",
        backstory="You route procurement questions to the right specialist.",
        llm=llm,
        allow_delegation=False,
    )
    route_task = Task(
        description=(
            "User question: {question}\n\n"
            "Return exactly one word: SQL or INSIGHT. "
            "Choose SQL when the answer requires supplier dataset calculations, "
            "filtering, grouping, ranking, or trend analysis. "
            "Choose INSIGHT for general procurement advice that needs no dataset lookup."
        ),
        expected_output="Exactly one word: SQL or INSIGHT",
        agent=router_agent,
    )
    crew = Crew(
        agents=[router_agent],
        tasks=[route_task],
        process=Process.sequential,
        verbose=False,
    )
    verdict = str(crew.kickoff(inputs={"question": question})).strip().upper()
    return "INSIGHT" if "INSIGHT" in verdict and "SQL" not in verdict else "SQL"


def _run_sql_path(llm: LLM, question: str) -> str:
    """Full path: generate + execute SQL, then summarise into business insight."""
    sql_agent = Agent(
        role="SQL Analyst",
        goal="Generate and run safe DuckDB read-only SQL against supplier data.",
        backstory="You are an expert at procurement analytics SQL.",
        llm=llm,
        tools=[get_schema, execute_sql],
        allow_delegation=False,
    )
    insight_agent = Agent(
        role="Procurement Insight Analyst",
        goal="Summarize SQL results into direct business insights without inventing values.",
        backstory="You explain findings for sourcing and pricing decisions.",
        llm=llm,
        allow_delegation=False,
    )
    sql_task = Task(
        description=(
            "User question: {question}\n\n"
            "1) Use get_schema to inspect available columns.\n"
            "2) Create one safe read-only DuckDB SQL query.\n"
            "3) Execute it using execute_sql.\n"
            "4) Return two sections only:\n"
            "SQL:\n<query>\n\nRESULT:\n<markdown table or (no rows)>"
        ),
        expected_output="SQL and RESULT sections.",
        agent=sql_agent,
    )
    insight_task = Task(
        description=(
            "User question: {question}\n\n"
            "Using previous task output, provide:\n"
            "1) Direct answer\n"
            "2) One concise insight\n"
            "3) One follow-up analysis suggestion"
        ),
        expected_output="Three short bullets: answer, insight, next analysis.",
        agent=insight_agent,
        context=[sql_task],
    )
    crew = Crew(
        agents=[sql_agent, insight_agent],
        tasks=[sql_task, insight_task],
        process=Process.sequential,
        verbose=False,
    )
    return str(crew.kickoff(inputs={"question": question}))


def _run_insight_path(llm: LLM, question: str) -> str:
    """Lightweight path for questions that need no dataset lookup."""
    insight_agent = Agent(
        role="Procurement Insight Analyst",
        goal="Answer general procurement questions clearly without inventing data.",
        backstory="You advise sourcing and pricing teams.",
        llm=llm,
        allow_delegation=False,
    )
    insight_task = Task(
        description=(
            "User question: {question}\n\n"
            "Answer directly and concisely. If the question would need specific "
            "supplier figures you do not have, say so rather than inventing numbers."
        ),
        expected_output="A concise, direct answer.",
        agent=insight_agent,
    )
    crew = Crew(
        agents=[insight_agent],
        tasks=[insight_task],
        process=Process.sequential,
        verbose=False,
    )
    return str(crew.kickoff(inputs={"question": question}))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Supplier Intelligence multi-agent runner")
    parser.add_argument("--question", required=True, help="User analytics question")
    parser.add_argument("--db", default="supplier_data.duckdb", help="DuckDB file path")
    parser.add_argument("--table", default="supplier_catalog", help="Table or view name")
    parser.add_argument("--source-csv", default=None, help="Optional CSV path for direct analysis with DuckDB read_csv_auto")
    parser.add_argument("--base-url", default=None, help="LM Studio base URL")
    parser.add_argument("--model", default=None, help="LM Studio model name")
    parser.add_argument("--api-key", default=None, help="LM Studio API key")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    output = run_supplier_agents(
        question=args.question,
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
        db_path=args.db,
        table=args.table,
        source_csv=args.source_csv,
    )
    print(output)
