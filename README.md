# Pricing Model Agent

> A **privacy-first, multi-agent procururement analytics platform** that combines structured SQL analytics with unstructured document retrieval to deliver business-ready supplier insights.

## Overview

This project is a **rapid prototype** built to validate business value in supplier pricing and procurement intelligence. It runs entirely **locally** by default (no data leaves your network), combining:

- **DuckDB** for deterministic, fast SQL analytics over structured procurement data
- **ChromaDB** for semantic search over policies, contracts, and unstructured documents
- **CrewAI** multi-agent orchestration for hybrid SQL + RAG (retrieval-augmented generation) answers
- **Gradio** web UI for interactive exploration
- **LM Studio** local LLM endpoint (or Azure OpenAI) for natural language query understanding

Perfect for:
- Supplier spend analysis and benchmarking
- Price anomaly detection and forecasting
- Payment risk assessment
- Policy/contract compliance Q&A
- Procurement sourcing workflows

---

## Quick Start

### Prerequisites

- Python 3.10+
- Virtual environment (recommended)
- **LM Studio** running locally with a loaded chat model (default: `http://127.0.0.1:1234`)
  - Or configure Azure OpenAI endpoint via `LMSTUDIO_BASE_URL`

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/ShiyuanZhangzsyzsy/Supplier-Intelligence-Agent.git
   cd "pricing model agent"
   ```

2. **Create and activate virtual environment**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Start LM Studio** (if using local model)
   - Open LM Studio desktop app
   - Load your preferred chat model
   - Keep it running on `http://127.0.0.1:1234`

### Run the UI

```powershell
.\.venv\Scripts\python.exe .\web_ui.py
```

Then open your browser to: **http://127.0.0.1:7860**

---

## Features

### 📊 Chat & Data Tab
- Natural language questions over procurement data
- Automatic routing to **SQL**, **RAG**, or **HYBRID** (SQL + documents) mode
- Tenant-isolated results with read-only query safety

**Example questions:**
- "Top suppliers by total spend over last 12 months"
- "Categories with highest unit price variance"
- "Any supplier showing unusual pricing behavior"

### 🔍 Advanced Analytics Panel
- **Price Anomalies**: Isolation Forest detection on supplier pricing patterns
- **Forecasting**: Holt-Winters demand/spend prediction (with backtesting)
- **Payment Risk**: Probabilistic late-payment scoring using RandomForest classification

### 📋 Runtime Trace
- Step-by-step execution log of how answers are produced
- View SQL queries, RAG retrieval results, and agent reasoning
- Transparency for troubleshooting and explainability

### 🛡️ Privacy by Design
- UI runs on localhost (127.0.0.1:7860) by default; never public
- Data stored in tenant-isolated DuckDB + ChromaDB indexes
- No data leaves the network unless explicitly configured
- Read-only SQL enforcement prevents accidental data modification

---

## Architecture

See [PROJECT_PIPELINE_GRAPH.md](PROJECT_PIPELINE_GRAPH.md) for the full execution flow.

**High-level:**
```
User Question (Gradio UI)
    ↓
Route: SQL / RAG / HYBRID?
    ├─ SQL route        → LM SQL generation → DuckDB read-only execution
    ├─ RAG route        → ChromaDB semantic search → answer synthesis
    └─ HYBRID route     → Both + correlation
    ↓
Runtime Trace (logged)
    ↓
Answer + Evidence (back to UI)
```

### Technology Stack
| Component | Technology | Purpose |
|-----------|-----------|---------|
| **UI** | Gradio | Interactive web interface |
| **Structured Analytics** | DuckDB | Fast SQL analytics, deterministic answers |
| **Unstructured Retrieval** | ChromaDB | Semantic document search, policy Q&A |
| **Agent Orchestration** | CrewAI | Multi-step reasoning, tool coordination |
| **LLM Gateway** | LM Studio or Azure OpenAI | Natural language understanding |
| **Multi-tenancy** | Local file isolation | Tenant databases & RAG stores |

---

## Project Structure

```
.
├── web_ui.py                          # Gradio web application entry point
├── supplier_agents.py                 # CrewAI multi-agent orchestration
├── supplier_agent_tools.py            # SQL execution + schema tools
├── rag_agent_tools.py                 # Document search tools
├── analytics_duckdb.py                # Advanced analytics (anomalies, forecasting, risk)
├── lmstudio_duckdb_bridge.py         # LM Studio client + SQL generation
├── multi_file_ingestion.py            # Bulk structured data ingest
├── rag_store.py                       # ChromaDB indexing & retrieval
├── ingestion_manifest.py              # Deduplication & audit trail
├── resilient_ingestion.py             # Single-file CSV/Excel loading
├── PROJECT_PIPELINE_GRAPH.md          # Full execution flow diagram
├── data/                              # CSV & document samples
├── tenants/                           # Multi-tenant data stores
│   └── default_tenant/
│       ├── databases/                 # DuckDB files
│       └── rag_store/                 # ChromaDB persistent index
├── agent_example/                     # Example multi-user agent setup
└── .env                               # Environment config (optional)
```

---

## Configuration

### Environment Variables (`.env`)

```bash
# LM Studio (default)
LMSTUDIO_BASE_URL=http://127.0.0.1:1234
LMSTUDIO_MODEL=local-model
LMSTUDIO_API_KEY=lm-studio

# Or use Azure OpenAI
# LMSTUDIO_BASE_URL=https://your-azure-instance.openai.azure.com/
# LMSTUDIO_API_KEY=your-azure-key
# LMSTUDIO_MODEL=gpt-4

# Tenant root directory
SUPPLIER_TENANT_ROOT=tenants

# Query tuning
LMSTUDIO_SQL_MAX_TOKENS=96
LMSTUDIO_SUMMARY_MAX_CHARS=3000
```

---

## Usage Examples

### 1. Basic Query (Chat & Data Tab)

1. Open UI at `http://127.0.0.1:7860`
2. Go to **Chat & Data** tab
3. In **Tenant Database Manager**, select:
   - Tenant: `default_tenant`
   - Active Database: Your `.duckdb` file
   - Data Mode: "Use existing imported data only"
4. Ask a question: _"What is the total spend by supplier in the last 6 months?"_
5. View **Runtime Trace** to see the execution path

### 2. Ingest New Data

1. Go to **Data Ingestion** tab
2. Choose scope: **Structured** (CSV/Excel)
3. Select **"Ingest all structured files in folder"**
4. Point to your `data/structured data/` directory
5. Monitor deduplication, schema validation, and table creation
6. Query immediately in Chat & Data tab

### 3. Run Advanced Analytics

1. Go to **Advanced Analytics** tab
2. Select pricing table with `[supplier_id, unit_price, quantity, total_amount]`
3. Choose analysis type: **Price Anomalies** / **Forecasting** / **Payment Risk**
4. Review results and interpretation notes

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **No answer appears** | Verify LM Studio is running and model is loaded. Click "Refresh LM Models" in UI. |
| **Data is missing** | Confirm active DB path in Tenant Database Manager. Check `.duckdb` file exists. |
| **Connection refused** | Ensure LM Studio listens on `http://127.0.0.1:1234` or update `LMSTUDIO_BASE_URL`. |
| **SQL query fails** | Check table/column names in Runtime Trace. Ingestion manifest shows available tables. |
| **RAG returns no results** | Ensure unstructured documents are indexed. Use Data Ingestion tab to ingest folder. |

---

## Roadmap & Deployment

This prototype is **intentionally optimized for speed of validation**. Production hardening roadmap:

- **Phase 1 (Now)**: Validate business value with current stack
- **Phase 1.5**: Add governance (SQL guardrails, row/column redaction, audit logs)
- **Phase 2**: Containerize for Azure deployment (App Service, Container Instances)
- **Phase 3**: Pilot LanceDB for hybrid SQL + vector workloads
- **Phase 4**: Full production architecture with MCP enforcement boundary

See [move_to_Azure_plan.txt](move_to_Azure_plan.txt) for the full deployment strategy.

---

## Contributing

Contributions welcome! Please:
1. Create a feature branch from `master`
2. Include unit tests for new analytics or ingestion logic
3. Update runtime traces if query or tool behavior changes
4. Submit a pull request with clear description

---

## License

[Specify your license here, e.g., MIT, Apache-2.0]

---

## Support & Questions

- **Issues & Bugs**: Open a GitHub issue with reproducible steps
- **Questions**: Start a discussion or check existing issues
- **Architecture**: See [PROJECT_PIPELINE_GRAPH.md](PROJECT_PIPELINE_GRAPH.md) and [move_to_Azure_plan.txt](move_to_Azure_plan.txt)

---

**Built with ❤️ for procurement transparency and speed.**
