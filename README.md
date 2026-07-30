# Ticket Medallion Pipeline

**Senior Data Engineer Take-Home Assignment**

A medallion architecture pipeline (Bronze → Silver → Gold) for ~10,000 facility maintenance tickets, accelerated by AI agents for data quality profiling and semantic classification.

---

## 1. Architecture

```
                          data/raw_tickets.csv
                          (~10,280 rows, 13 cols)
                          READ-ONLY — never modified
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  BRONZE (schema: bronze)                                         │
│                                                                  │
│  raw_tickets                                                     │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ All 13 columns as TEXT (schema-on-read, zero data loss)    │  │
│  │ + ingested_at      TIMESTAMPTZ    ← lineage: when loaded   │  │
│  │ + source_file       TEXT           ← lineage: which file   │  │
│  │ + row_hash          TEXT           ← dedup tracking (SHA256)│  │
│  └────────────────────────────────────────────────────────────┘  │
│  Idempotency: TRUNCATE + full reload                             │
└──────────────────────────────┬───────────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
     ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
     │ Data Quality │  │  Semantic    │  │  (extensible)│
     │ Agent        │  │  Classify    │  │              │
     │              │  │  Agent       │  │              │
     │ Profiles     │  │  98 messy    │  │              │
     │ bronze →     │  │  categories  │  │              │
     │ proposes 7   │  │  → 15 clean  │  │              │
     │ cleaning     │  │  groups      │  │              │
     │ rules + why  │  │              │  │              │
     └──────┬───────┘  └──────┬───────┘  └──────────────┘
            │                 │
            │ cleaning rules  │ category mapping
            │ + justifications│
            ▼                 ▼
┌──────────────────────────────────────────────────────────────────┐
│  SILVER (schema: silver)                                         │
│                                                                  │
│  tickets_cleaned                                                 │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ ticket_id           TEXT (PK)                              │  │
│  │ created_at          TIMESTAMPTZ    ← parsed from 7 formats │  │
│  │ resolved_at         TIMESTAMPTZ    ← parsed from 7 formats │  │
│  │ category_raw        TEXT           ← original (for audit)  │  │
│  │ category_normalized TEXT           ← agent-classified      │  │
│  │ priority            TEXT           ← CRITICAL/HIGH/MED/LOW │  │
│  │ status              TEXT           ← validated             │  │
│  │ building            TEXT                                  │  │
│  │ description         TEXT                                  │  │
│  │ submitted_by        TEXT                                  │  │
│  │ assigned_to         TEXT                                  │  │
│  │ resolution_notes    TEXT                                  │  │
│  │ cost                DECIMAL(12,2)  ← cleaned ($, N/A)     │  │
│  │ sla_hours           INTEGER        ← cleaned (999 → NULL) │  │
│  │ data_quality_flags  JSONB          ← per-row quality notes│  │
│  │ silver_processed_at TIMESTAMPTZ    ← lineage              │  │
│  └────────────────────────────────────────────────────────────┘  │
│  Dedup: 823 duplicate tickets excluded                           │
│  Validation: resolved_at ≥ created_at, valid statuses            │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  GOLD (schema: gold)                                             │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ 1. monthly_ticket_kpis                                    │   │
│  │    Monthly trends: volume, resolution rate, avg cost,     │   │
│  │    avg resolution days, SLA breach %                      │   │
│  │    → Executive dashboard view                             │   │
│  ├───────────────────────────────────────────────────────────┤   │
│  │ 2. category_analytics                                     │   │
│  │    Per category: ticket count, avg cost, avg SLA hours,   │   │
│  │    SLA breach %, most-affected building                   │   │
│  │    → Budget allocation & preventive maintenance planning  │   │
│  ├───────────────────────────────────────────────────────────┤   │
│  │ 3. building_health_scorecard                              │   │
│  │    Per building: total tickets, open tickets,             │   │
│  │    avg open age (days), avg resolution days, SLA breach % │   │
│  │    → Resource allocation & facility health monitoring     │   │
│  └───────────────────────────────────────────────────────────┘   │
│  All models use ON CONFLICT DO UPDATE for idempotent refresh     │
└──────────────────────────────────────────────────────────────────┘
```

### Design Decisions

**Why PostgreSQL?** The assignment suggested it. PostgreSQL gives us proper schema separation (`CREATE SCHEMA`), typed DDL, JSONB for semi-structured quality flags, and materialized-view-style aggregations. For 10K rows it's overkill — DuckDB or even pandas-to-Parquet would work — but PostgreSQL demonstrates production discipline: schemas, constraints, upsert semantics, and concurrent access. At this scale, the choice is about showing you know how to design for a real RDBMS.

**Why not LangGraph / CrewAI / Airflow?** The pipeline has 3 sequential stages on 10K rows. A single Python script with clear function boundaries is the right tool. Adding LangGraph for 3 steps is like Kubernetes for a static page. At production scale with incremental loads, I'd introduce Airflow/Dagster + dbt.

**Why TRUNCATE + full reload for idempotency?** Simplest correct thing. At this scale, a full reload takes seconds. At 100x scale, I'd switch to merge-on-hash with watermark columns.

**Why deterministic agent fallback?** The agents work without API keys — the interviewer can run `make run` and see everything. The LLM prompts are generated and saved for review. This balances "show me the prompt engineering" with "it must actually run."

---

## 2. Agent Assessment

### Agent B: Data Quality Agent

**What it does:** Profiles the bronze layer (null rates, date format distribution, cost outliers, category cardinality) and proposes cleaning rules with natural-language justification.

**Sample input:**
```
Column: created_at
- 7 distinct date formats detected
- 0.1% unparseable ("TBD")
- 48% NULL in resolved_at
```

**Sample output:**
```json
{
  "rule_id": "DQ-001",
  "column": "created_at, resolved_at",
  "rule": "Multi-format date parser: detect ISO-T, ISO-space, US-slash, US-dash, Euro-dash, Unix timestamp, date-only. Flag unparseable values as NULL with data_quality_flag.",
  "justification": "Found 7 distinct date formats including invalid text values. A single-format parser would lose data. Cascading parser preserves maximum information.",
  "implementation": "python: dateutil.parser.parse() with fallback chain"
}
```

**Honest assessment: This saved me ~15 minutes.** Profiling 13 columns manually takes time, and the agent's structured output (rule_id + justification + implementation) creates an auditable, repeatable artifact. The deterministic mode means it runs in <1 second with no API cost. **However:** for 10K rows, a good data engineer would write similar profiling code anyway. The agent's real value is the *natural-language justification* — explaining WHY a rule matters, which makes the pipeline self-documenting. At scale with 100+ columns, the agent would be indispensable.

**What I'd trust vs. override:** The rules it proposes are sound — they're based on statistical profiling. I'd trust the rule detection but review the implementation before committing to production.

---

### Agent C: Semantic Classification Agent

**What it does:** Takes 98 unique, messy category spellings from the bronze layer and maps them to 15 clean business categories using semantic understanding (e.g., knowing that "vertical transport" = "lift" = "elevator/escalator" all mean Elevator).

**Sample input:** (5 of 98 categories)
```
elevator, ELEVATOR, elevator/escalator, vertical transport, lift
hvac, HVAC, A/C, a/c, climate control, heating/cooling
```

**Sample output:**
```json
{
  "elevator": {"target": "Elevator", "confidence": 1.0, "reasoning": "Direct match"},
  "vertical transport": {"target": "Elevator", "confidence": 1.0, "reasoning": "Industry synonym for elevator equipment"},
  "lift": {"target": "Elevator", "confidence": 1.0, "reasoning": "British English synonym for elevator"},
  "climate control": {"target": "HVAC", "confidence": 0.95, "reasoning": "Subset of HVAC — could also be general, but context favors HVAC"}
}
```

**Honest assessment: This saved me ~20 minutes and is the strongest agent.** Manually building a mapping table for 98 categories is tedious, error-prone, and requires domain knowledge (is "vertical transport" an elevator or a shuttle bus?). The agent handles synonyms, case variants, and abbreviations that would take a human 15-20 minutes to map. **The deterministic mode uses a pre-curated mapping that I originally generated with LLM assistance, then reviewed and committed as code.** This is the right pattern: AI proposes, human reviews, code executes deterministically.

**What I'd trust vs. override:** The agent's category groupings are ~95% correct. I'd review edge cases (e.g., "indoor air quality" → HVAC vs. Health & Environmental) and flag ambiguous mappings for human review. The agent's confidence scores are useful for triaging what needs human attention.

**Cost awareness:** The deterministic mode costs $0 — the mapping is a Python dict. The LLM-assisted mode would cost ~$0.02 per run (98 categories × ~50 tokens each). For a one-time mapping exercise, that's negligible. For ongoing classification of new categories arriving daily, I'd batch and cache aggressively.

---

### Why I didn't build Agents A and D

| Agent | Decision | Reason |
|-------|----------|--------|
| (a) Schema Inference | **Skipped** | 13 columns are trivial to type by hand. A human writes the DDL in 3 minutes. The agent adds latency and API cost for zero time savings at this scale. |
| (d) Gold Layer Design | **Skipped** | The gold aggregations require business context the agent doesn't have. A human with domain knowledge chooses better metrics. I did implement the aggregations, just without an agent layer — the SQL is straightforward. |

---

## 3. What Changes at 100x Scale (1M+ rows, daily incremental loads)

### Storage
- **Partitioning:** Partition `silver.tickets_cleaned` by `created_at` month. This keeps scans bounded for incremental loads.
- **Indexing:** Add composite indexes on `(building, status)`, `(category_normalized, created_at)`, and `(assigned_to, created_at)` for common query patterns.
- **Data lake integration:** Bronze would land in object storage (S3/MinIO) as Parquet files, not PostgreSQL. PostgreSQL stores only silver+gold.

### Orchestration
- **Airflow / Dagster / Prefect:** Replace the single Python script with a DAG. Bronze runs hourly, silver after bronze succeeds, gold after silver succeeds.
- **dbt for transformations:** Silver and gold SQL would move to dbt models with built-in testing, documentation, and lineage tracking. The Python date parsing could become a dbt Python model.

### Incremental Strategy
- **Bronze:** Append-only. New files arrive in a landing zone, get ingested with `ingested_at` timestamp. No truncation.
- **Silver:** MERGE on `ticket_id` using a watermark (`WHERE silver_processed_at > last_run OR ticket_id IN (SELECT ticket_id FROM bronze WHERE ingested_at > last_run)`).
- **Gold:** Materialized views refreshed on schedule, or incremental aggregations using dbt's incremental materialization.

### Agent Changes
- **Batching:** The Data Quality Agent would profile a sample (not all rows) — reservoir sampling for statistical validity at 1% sample size.
- **Caching:** The Semantic Classification Agent's mapping would be cached. Only new, unseen categories trigger an LLM call. 99% of classifications use the cached mapping.
- **Cost:** At 1M rows with 200 new categories/month, LLM costs would be ~$0.05/month for classification. Data quality profiling on samples adds ~$0.02/run.
- **Async:** Agent calls would be async background jobs, not blocking the pipeline. The pipeline runs with the last-known-good mapping while agents refine suggestions.
- **Human-in-the-loop:** Schema changes and category mapping updates would require approval before promotion to production.

### Observability
- Row counts per layer with drift detection
- Null rate deltas (did cleaning suddenly miss more rows?)
- Agent suggestion queue depth
- Token usage and cost per agent run
- SLA for pipeline freshness (bronze within 5 min of file arrival, silver within 10 min)

---

## 4. How to Run

### Prerequisites
- Docker + Docker Compose
- Python 3.9+
- `pip3 install -r requirements.txt`
- The dataset: `data/raw_tickets.csv` is a symlink to the original CSV.
  If cloning this repo, update the symlink: `ln -sf /path/to/raw_tickets.csv data/raw_tickets.csv`

### Single Command
```bash
make run
```

This does:
1. `docker-compose up -d` — starts PostgreSQL 16
2. Waits for PostgreSQL to be ready
3. `python3 src/main.py` — runs the full pipeline

### Step by Step
```bash
# 1. Start PostgreSQL
docker-compose up -d

# 2. Install Python deps (first time only)
make install

# 3. Run the full pipeline
python3 src/main.py

# 4. Query results
make psql
# Then run:
#   SELECT * FROM gold.monthly_ticket_kpis;
#   SELECT * FROM gold.category_analytics;
#   SELECT * FROM gold.building_health_scorecard;

# 5. Stop everything
make down
```

### Options
```bash
python3 src/main.py --skip-agents       # Pipeline only, no agent analysis
python3 src/main.py --agent-mode prompt_only  # Output LLM prompts to agent_outputs/
python3 src/main.py --bronze-only       # Only run bronze ingestion
```

### What you'll see
The pipeline logs every stage with row counts:
```
2026-07-30 16:00:00 [INFO   ] main                     MEDALLION PIPELINE — Facility Ticket Data
2026-07-30 16:00:00 [INFO   ] main                     Step 0: Initializing database schemas...
2026-07-30 16:00:01 [INFO   ] src.pipeline.bronze      === BRONZE LAYER: Starting ingestion ===
2026-07-30 16:00:01 [INFO   ] src.pipeline.bronze      Read 10280 rows from .../data/raw_tickets.csv
2026-07-30 16:00:03 [INFO   ] src.pipeline.bronze      Bronze ingestion complete: 10280 rows loaded.
2026-07-30 16:00:03 [INFO   ] src.agents.data_quality  === AGENT: Data Quality Agent ===
2026-07-30 16:00:03 [INFO   ] src.agents.data_quality  Generated 7 cleaning rules → agent_outputs/...
2026-07-30 16:00:03 [INFO   ] src.agents.semantic_cla  === AGENT: Semantic Classification Agent ===
2026-07-30 16:00:03 [INFO   ] src.agents.semantic_cla  Coverage: 95.9% (94/98 mapped)
2026-07-30 16:00:03 [INFO   ] src.pipeline.silver      === SILVER LAYER: Starting transformation ===
2026-07-30 16:00:05 [INFO   ] src.pipeline.silver      Silver transformation complete.
2026-07-30 16:00:05 [INFO   ] src.pipeline.gold        === GOLD LAYER: Building aggregations ===
2026-07-30 16:00:05 [INFO   ] main                     ✓ Pipeline complete.
```

### Verify Idempotency
```bash
python3 src/main.py    # First run
python3 src/main.py    # Second run — same output, same row counts
```

---

## 5. Project Structure

```
.
├── docker-compose.yml         # PostgreSQL 16 (Alpine)
├── requirements.txt           # psycopg2-binary, python-dateutil, pandas
├── Makefile                   # make run / make psql / make clean
├── README.md                  # ← You are here
├── data/
│   └── raw_tickets.csv        # Symlink to original dataset (read-only)
├── src/
│   ├── config.py              # Configuration, paths, DB settings
│   ├── db.py                  # Connection management, schema DDL
│   ├── main.py                # Orchestrator — entry point
│   ├── pipeline/
│   │   ├── bronze.py          # Bronze: raw ingestion + lineage
│   │   ├── silver.py          # Silver: cleanse, type, dedup, validate
│   │   └── gold.py            # Gold: 3 aggregation models
│   └── agents/
│       ├── data_quality.py    # Agent B: profile + propose cleaning rules
│       └── semantic_classify.py  # Agent C: normalize 98 → 15 categories
└── agent_outputs/             # Agent outputs (gitignored, generated at runtime)
    ├── data_quality_rules.json
    └── semantic_classification_result.json
```

---

## 6. Data Quality Rules Applied

The pipeline applies these rules automatically. See `agent_outputs/data_quality_rules.json` for justifications.

| Rule ID | Column | What it does |
|---------|--------|-------------|
| DQ-001 | created_at, resolved_at | Multi-format date parser (7 formats) |
| DQ-002 | category | Normalize 98 spellings → 15 business categories |
| DQ-003 | priority | Normalize to CRITICAL/HIGH/MEDIUM/LOW (4 tiers) |
| DQ-004 | cost | Clean $/commas, nullify negative + sentinel values |
| DQ-005 | sla_hours | Nullify 999 sentinel, cast to INTEGER |
| DQ-006 | resolution_notes | Detect and exclude ~823 duplicate tickets |
| DQ-007 | resolved_at vs created_at | Flag impossible resolved-before-created dates |

---

## 7. Key Tradeoffs & Honest Assessment

**What agents do well:**
- Semantic classification saved real time — 98 messy categories is exactly where LLMs shine
- Data quality profiling gave structured, justified rules instead of ad-hoc cleaning
- Both agents produce auditable JSON artifacts — the pipeline is self-documenting

**What agents don't help with:**
- Schema inference: 13 columns don't need an LLM. A human writes DDL faster.
- Gold layer design: Aggregations need business context. The agent can suggest but can't decide.
- The pipeline itself: For 10K rows, Python scripts with TRUNCATE + INSERT are simpler and faster than any agent-orchestrated workflow.

**What I'd do differently with more time:**
- Add an agent evaluation harness — a test set of known-bad rows to score agent accuracy
- Implement the "prompt_only → human review → commit mapping" workflow as code
- Add dbt for transformation testing and documentation
- Implement incremental loads with watermark columns instead of full reloads
