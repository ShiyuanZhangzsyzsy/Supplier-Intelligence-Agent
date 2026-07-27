# Supplier Intelligence Agent — Pipeline Graph

```mermaid
flowchart TB
    U[User in Browser] --> UI[Gradio UI\nweb_ui.py]

    UI --> CFG[Runtime config\nDB path, table, mode, LM settings]
    CFG --> MODE{Data mode}

    MODE -->|Query file directly| DIRECT[DuckDB temp view over file\nsql_safety.py]
    MODE -->|Ingest file| INGEST[CSV/Excel ingestion\nresilient_ingestion.py]
    MODE -->|Use existing data| EXIST[Use active DuckDB database]

    INGEST --> DB[(DuckDB database)]
    DIRECT --> DB
    EXIST --> DB

    UI --> ROUTE{Router agent\nsupplier_agents.py}

    ROUTE -->|SQL path| SQLA[SQL analyst agent\n+ get_schema / execute_sql tools]
    SQLA --> GUARD[Read-only SQL guardrails\nsql_safety.py]
    GUARD --> DB
    SQLA --> INS1[Insight agent\nbusiness summary]

    ROUTE -->|INSIGHT path| INS2[Insight agent\ndirect advice, no lookup]

    INS1 --> ANSWER[Answer returned to UI]
    INS2 --> ANSWER
    ANSWER --> UI
```

## Notes

- The router **branches**: only the SQL path touches the database; the INSIGHT
  path answers directly without a dataset lookup.
- All model-generated SQL passes through the shared guardrails in `sql_safety.py`
  before execution, and existing databases are opened read-only.
- `lmstudio_duckdb_bridge.py` offers the same question→SQL→result flow without
  the agent layer, for quick testing.
