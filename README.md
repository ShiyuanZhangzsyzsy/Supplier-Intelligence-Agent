# Supplier Intelligence Agent

A privacy-first prototype that answers natural-language questions about supplier
and procurement data by generating safe, read-only SQL and running it locally
against DuckDB. It runs entirely on your machine by default — the language model
is served from a local [LM Studio](https://lmstudio.ai/) endpoint, so no data
leaves your network.

> **Scope note.** This repository contains the **structured SQL analytics path**:
> a Gradio UI, a CrewAI router that branches between a full SQL pipeline and a
> lightweight advice path, a read-only SQL safety layer, and CSV/Excel ingestion.
> Retrieval-augmented generation (RAG) over unstructured documents and the
> advanced statistical analytics (anomaly detection, forecasting) are on the
> roadmap below, not yet in this repo.

---

## What it does

- Takes a plain-English question such as *"Top 10 suppliers by total spend this year"*.
- A **router agent** classifies the question as needing dataset analytics (`SQL`)
  or general advice (`INSIGHT`) and **branches accordingly** — only the relevant
  path runs.
- On the SQL path, a **SQL analyst agent** inspects the schema, writes one
  read-only DuckDB query, executes it through a guarded tool, and an **insight
  agent** turns the result into a short business answer without inventing values.
- The whole flow runs against a local model, keeping procurement data on-device.

---

## Safety model

Because the model writes SQL that then runs against your data, query safety is
enforced in depth (see `sql_safety.py`):

1. **Prefix allowlist** — a statement must start with `SELECT`, `WITH`, `SHOW`,
   `DESCRIBE`, or `PRAGMA`.
2. **Keyword blocklist** — any of `INSERT, UPDATE, DELETE, DROP, ALTER, CREATE,
   REPLACE, TRUNCATE, ATTACH, DETACH, COPY, CALL` is rejected.
3. **Single-statement rule** — stacked statements (`;`) are rejected.
4. **Engine-level read-only** — existing databases are opened with DuckDB's
   `read_only=True`, so the engine refuses writes even if a check were bypassed.

---

## Architecture

```
User question (Gradio UI, web_ui.py)
        |
        v
Router agent  ──►  "SQL" or "INSIGHT"?   (supplier_agents.py)
        |
        ├─ SQL path
        |     SQL analyst agent → get_schema / execute_sql tools
        |                          (supplier_agent_tools.py + sql_safety.py)
        |                       → DuckDB read-only execution
        |     Insight agent     → business summary (no invented values)
        |
        └─ INSIGHT path
              Insight agent     → direct advice, no dataset lookup
        |
        v
Answer returned to the UI
```

`lmstudio_duckdb_bridge.py` provides an alternative, single-call
(non-agentic) question→SQL→result flow using the same safety layer, useful for
quick testing without the CrewAI overhead.

---

## Project structure

```
.
├── web_ui.py                  # Gradio web application entry point
├── supplier_agents.py         # CrewAI router + SQL and INSIGHT paths
├── supplier_agent_tools.py    # get_schema / execute_sql agent tools
├── sql_safety.py              # shared read-only SQL validation + CSV views
├── lmstudio_duckdb_bridge.py  # non-agentic LM Studio → SQL → result flow
├── resilient_ingestion.py     # CSV/Excel → DuckDB loading (encoding-resilient)
├── duckdb_query_cli.py        # small interactive DuckDB SQL CLI
├── duckdb_smoke_test.py       # smoke test for the DuckDB layer
├── PROJECT_PIPELINE_GRAPH.md  # mermaid diagram of the flow
├── requirements.txt
└── LICENSE
```

---

## Quick start

**Prerequisites:** Python 3.10+, and [LM Studio](https://lmstudio.ai/) running
locally with a chat model loaded (default endpoint `http://127.0.0.1:1234`).

```bash
# 1. Clone
git clone https://github.com/ShiyuanZhangzsyzsy/Supplier-Intelligence-Agent.git
cd Supplier-Intelligence-Agent

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start LM Studio, load a chat model, keep the local server running.

# 5. Launch the UI
python web_ui.py
```

Then open `http://127.0.0.1:7860`.

You can also run a single question from the command line:

```bash
python supplier_agents.py --question "Top 5 suppliers by spend" \
  --source-csv path/to/your_data.csv
```

---

## Configuration

Configure the local model via environment variables or a `.env` file (a
`.gitignore` keeps `.env` and any local data out of version control):

```bash
LMSTUDIO_BASE_URL=http://127.0.0.1:1234   # local LM Studio server
LMSTUDIO_MODEL=local-model                # model identifier as shown in LM Studio
LMSTUDIO_API_KEY=lm-studio                 # placeholder; LM Studio ignores it
LMSTUDIO_TIMEOUT_SECONDS=90
```

To use a hosted OpenAI-compatible endpoint instead, point `LMSTUDIO_BASE_URL`
and `LMSTUDIO_API_KEY` at that service. Note this sends data off-device and
trades away the privacy-first property.

---

## Roadmap

The following are planned extensions, not yet implemented in this repository:

- **RAG path** — semantic search over policies and contracts (e.g. ChromaDB),
  plus a hybrid SQL + document mode.
- **Advanced analytics** — price-anomaly detection, spend forecasting, and
  payment-risk scoring.
- **Multi-tenancy** — per-tenant isolated databases and document stores.
- **Deployment** — containerisation for cloud hosting behind an auth boundary.

---

## License

Released under the MIT License. See [LICENSE](LICENSE).
