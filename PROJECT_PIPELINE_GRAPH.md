# Pricing Model Agent Pipeline Graph

```mermaid
flowchart TB
    U[User in Browser] --> UI[Gradio UI\nweb_ui.py]

    UI --> CFG[Tenant + Runtime Config\nactive DB path, table, mode, LM settings]

    CFG --> MODE{Data Mode}

    MODE -->|Query file directly| DIRECT[DuckDB temp view over file\nresilient_ingestion.py]
    MODE -->|Ingest file/folder| INGEST[Structured ingestion\nresilient_ingestion.py + multi_file_ingestion.py]
    MODE -->|Unstructured ingest| RAGI[RAG ingest\nrag_store.py]
    MODE -->|Use existing imported data| EXIST[Use active tenant DB + existing RAG index]

    INGEST --> MANIFEST[Ingestion manifest + dedupe\ningestion_manifest.py]
    MANIFEST --> DB[(DuckDB tenant database\ntenants/<tenant>/databases/*.duckdb)]

    DIRECT --> DB
    EXIST --> DB

    RAGI --> CHROMA[(Chroma persistent store\ntenants/<tenant>/rag_store)]
    EXIST --> CHROMA

    UI --> ROUTE{Question path}

    ROUTE -->|Deterministic SQL path| SQLPATH[LM SQL generation + guardrails\nlmstudio_duckdb_bridge.py]
    SQLPATH --> SQLRUN[Read-only SQL execution\nsupplier_agent_tools.py]
    SQLRUN --> DB

    ROUTE -->|Multi-agent path| CREW[CrewAI orchestration\nsupplier_agents.py]
    CREW --> TOOLSQL[get_schema + run_sql tools\nsupplier_agent_tools.py]
    CREW --> TOOLRAG[search_documents tool\nrag_agent_tools.py]
    TOOLSQL --> DB
    TOOLRAG --> CHROMA

    DB --> ANALYTICS[Advanced analytics panels\nanalytics_duckdb.py]

    SQLRUN --> ANSWER[Business answer + evidence]
    CREW --> ANSWER
    ANALYTICS --> ANSWER
    ANSWER --> TRACE[Runtime trace capture\nweb_ui.py]
    TRACE --> UI
```

## Notes

- Structured data path uses DuckDB as source of truth for analytics and SQL answers.
- Unstructured data path uses Chroma for semantic retrieval in RAG answers.
- The UI can run deterministic SQL or multi-agent hybrid (SQL + RAG) flow.
- Runtime trace records execution steps for explainability.
