# Interview Prep — Ticket Medallion Pipeline

Repo: https://github.com/rishabhpyro/ticket-medallion-pipeline

---

## 30-Second Elevator Pitch

"I built a medallion architecture pipeline for ~10K messy facility maintenance tickets. Bronze ingests raw with lineage, Silver cleans and deduplicates with AI-assisted classification, Gold produces three business aggregations. I used PostgreSQL with Docker Compose, two AI agents — Data Quality and Semantic Classification — and deliberately kept the orchestration simple. The whole thing runs with one command, is idempotent, and I can explain exactly where agents saved time and where they didn't."

---

## The Data Problem

- 10,280 rows, 13 columns of facility tickets
- 7+ date formats mixed in one column
- 98 distinct category spellings that should be ~15 business groups
- Costs with `$`, `N/A`, and negative sentinels
- SLA values with `999` as a missing-data flag
- 823 duplicate tickets marked in free-text resolution notes
- Assignment: build medallion + minimum 2 AI agents, deliver as GitHub repo, 4-5 hour budget

---

## Architecture

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
              │                │
              ▼                ▼
     ┌─────────────┐  ┌──────────────┐
     │ Data Quality │  │  Semantic    │
     │ Agent        │  │  Classify    │
     │              │  │  Agent       │
     │ Profiles     │  │  104 messy   │
     │ bronze →     │  │  categories  │
     │ proposes 7   │  │  → 15 clean  │
     │ cleaning     │  │  groups      │
     │ rules + why  │  │              │
     └──────┬───────┘  └──────┬───────┘
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
│  │ created_at          TIMESTAMPTZ    ← parsed from 7+ formats│  │
│  │ resolved_at         TIMESTAMPTZ    ← parsed from 7+ formats│  │
│  │ category_raw        TEXT           ← original (for audit)  │  │
│  │ category_normalized TEXT           ← 15 business groups    │  │
│  │ priority            TEXT           ← CRITICAL/HIGH/MED/LOW │  │
│  │ status              TEXT           ← validated             │  │
│  │ building            TEXT                                  │  │
│  │ description         TEXT                                  │  │
│  │ submitted_by        TEXT                                  │  │
│  │ assigned_to         TEXT                                  │  │
│  │ resolution_notes    TEXT                                  │  │
│  │ cost                DECIMAL(12,2) ← cleaned               │  │
│  │ sla_hours           INTEGER        ← cleaned               │  │
│  │ data_quality_flags  JSONB          ← all quality issues    │  │
│  │ silver_processed_at TIMESTAMPTZ                           │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  GOLD (schema: gold)                                             │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ 1. monthly_ticket_kpis    — volume, resolution rate,       │  │
│  │    avg cost, avg resolution days, SLA breach %             │  │
│  │                                                            │  │
│  │ 2. category_analytics     — by category: volume, avg cost, │  │
│  │    SLA adherence, top building                             │  │
│  │                                                            │  │
│  │ 3. building_health        — open tickets, avg open age,    │  │
│  │    SLA breach rate, cost per ticket                        │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Pipeline Details

### Bronze Layer
- **Schema-on-read**: every column is TEXT, no data loss
- **Lineage metadata**: `ingested_at` (when), `source_file` (where from), `row_hash` (SHA-256 — enables dedup tracking and idempotency)
- **Idempotency**: TRUNCATE + full reload. For 10K rows this takes <1 second. At 1M+ rows with daily incremental loads, I'd switch to MERGE on row_hash with a `_loaded_at` watermark

### Silver Layer
- **Date parsing**: cascading parser — Unix timestamp → dateutil (ISO-T, ISO-space, US slash, US dash, Euro dash, AM/PM) → date-only fallback → flags TBD/N/A/??? as NULL
- **Category normalization**: 104 explicit mapping entries → 15 business categories, with 52-keyword fallback for mis-categorized long descriptions (some rows have full sentences in the category field — data entry errors)
- **Priority normalization**: 13 variants → 4 tiers (CRITICAL/HIGH/MEDIUM/LOW)
- **Cost cleaning**: strip `$` and commas, nullify `> $100K` outliers, flag negative/zero costs
- **SLA cleaning**: nullify 999 and -1 sentinels
- **Deduplication**: ~823 rows with "duplicate of ticket" in resolution_notes → excluded
- **Validation**: `resolved_at >= created_at`, unrecognized statuses flagged
- **Quality tracking**: all issues recorded in `data_quality_flags` JSONB column

### Gold Layer
1. **Monthly Ticket KPIs** — volume, resolution rate, avg cost, avg resolution days, SLA breach % → executive dashboard
2. **Category Analytics** — by normalized category with top building → resource allocation, preventive maintenance budgeting
3. **Building Health Scorecard** — open tickets count, avg age of open tickets, SLA breach rate → facility manager's operational view

---

## AI Agents

### Data Quality Agent
- Profiles bronze layer — distributions, null rates, outliers, cardinality
- Generates 7 cleaning rules (DQ-001 through DQ-007) with natural-language justification
- Outputs auditable JSON to `agent_outputs/`
- Two modes: deterministic (rule-based, zero API cost, <1 second) and prompt_only (outputs LLM prompt for human-in-the-loop review)
- Rules: date parsing, category normalization, priority normalization, cost cleaning, SLA cleaning, duplicate handling, temporal validation

### Semantic Classification Agent
- Takes 98 distinct raw category values → 15 business groups
- 104-entry mapping dict with 52-keyword fallback
- Handles synonyms: "vertical transport" = "lift" = "elevator/escalator" all → Elevator
- Handles garbage: ???, asdf, DELETE ME, test → nullified with flag
- **The mapping was originally generated with LLM assistance, human-reviewed, and committed as code** — AI proposes, human reviews, code executes deterministically

### Single Source of Truth
All category logic lives in `src/categories.py` — mapping, keywords, garbage detection, priority mapping, classification function. Silver pipeline, semantic agent, and verification harness all import from it. No copies, no drift.

---

## Why Each Decision

### Why PostgreSQL, not DuckDB?
DuckDB would be faster to set up — zero config, no Docker, just `pip install`. I chose PostgreSQL because: it demonstrates production schema discipline (schemas, views, constraints, JSONB), the TEXT → TIMESTAMPTZ → typed layer progression maps cleanly to medallion, and an interviewer evaluating a Senior DE wants to see real RDBMS design. **Honest admission**: at 10K rows, DuckDB or pandas-to-Parquet would be perfectly fine. PostgreSQL wins for concurrent readers, materialized views, and incremental loads.

### Why not Spark?
10K rows. Spark's overhead (JVM startup, serialization, distributed execution planning) would take longer than the entire pipeline runtime. Spark makes sense at 100GB+, not 10K rows.

### Why no LangGraph / CrewAI / Airflow?
The assignment says "no over-engineering." For a 3-stage batch pipeline on 10K rows, a single Python script with clear function boundaries and logging is the right tool. Adding LangGraph for 3 sequential steps is like using Kubernetes to serve a static HTML page. At 100x scale, I'd add dbt for transformations and Airflow/Dagster for orchestration.

### Why TRUNCATE + full reload, not incremental?
10K rows insert in <1 second. No watermark columns to track, no CDC, no upsert logic to debug. Idempotency is trivial. The source is a static snapshot, not a streaming feed. At scale with daily incremental loads: MERGE on row_hash with a `_loaded_at` watermark column.

### Why 15 categories?
The data naturally clustered into these groups. Too few (e.g., 5) loses granularity — "HVAC" vs "Plumbing" are fundamentally different for facilities management. Too many (e.g., 30) defeats the purpose of normalization. 15 hits the sweet spot: each has meaningful volume, distinct SLA patterns, and clear business ownership.

### Why build agents B and C, but not A and D?
- **(a) Schema Inference**: SKIPPED. 13 columns are trivial to type by hand. DDL takes 3 minutes. Agent adds latency and API cost for zero time savings.
- **(b) Data Quality**: BUILT. Profiling 13 columns manually takes time. The agent's structured output (rule_id + justification + implementation) is auditable and self-documenting.
- **(c) Semantic Classification**: BUILT. This is where LLMs genuinely shine. 98 messy free-text categories → 15 groups. A human would spend 15-20 minutes building the mapping table. The agent does it in seconds.
- **(d) Gold Layer Design**: SKIPPED. Aggregations need business context the agent doesn't have. A human with domain knowledge writes better SQL.

---

## Interview Questions & Answers

### "Walk me through how a row flows from CSV to gold."

CSV → csv.DictReader → row_hash computed → INSERT into bronze.raw_tickets (all TEXT + lineage columns). Then: SELECT * from bronze → for each row: parse dates (cascading parser) → classify category (104-entry map → keyword fallback → garbage check → title-case last resort) → normalize priority → clean cost/SLA → check for duplicates → INSERT into silver.tickets_cleaned. Then: 3 aggregation queries on silver → INSERT/UPDATE into gold tables.

### "How do you know the pipeline is idempotent?"

Each layer uses TRUNCATE before full reload. Bronze has row hashes for verification. Gold uses ON CONFLICT DO UPDATE. The verify.py harness runs the pipeline twice and confirms identical output. Full idempotency testing of silver/gold would require a more rigorous harness — something I'd add with more time.

### "What happens if the CSV has 50,000 rows tomorrow?"

Nothing breaks. 50K rows is still sub-second for PostgreSQL. At ~500K rows, I'd add batch inserts (executemany) instead of row-by-row. At 5M+ rows, I'd switch to COPY protocol for bronze ingestion, add indexes to silver, and partition gold by month.

### "What if a new category appears that your mapping doesn't cover?"

The `classify_category()` function has four fallback layers: exact mapping → keyword matching (52 patterns) → garbage detection → title-case as last resort with an `unclassified_category` flag. In production, I'd add an alert on coverage dropping below a threshold.

### "How would you handle late-arriving data or backfills?"

For a full refresh pipeline on a static CSV, this isn't relevant. For incremental: I'd add a `_loaded_at` watermark column to bronze, process only rows with `ingested_at > last_watermark` in silver, use Slowly Changing Dimension patterns in gold, and maintain a replay window.

### "Did the AI agents actually save time?"

**Semantic classification**: genuinely saved ~20 minutes. Mapping 98 categories is tedious, error-prone manual work. **Data quality**: saved ~15 minutes. The structured rule-with-justification output is self-documenting. **Schema inference and gold design**: I skipped because they wouldn't save meaningful time. This honesty is what the evaluation wants.

### "What's the cost of running these agents?"

Deterministic mode: $0 — the mapping is a Python dict, the rules are from statistical thresholds. LLM-assisted mode: ~$0.02 per run for classification, ~$0.01 for profiling. At 100x scale with daily runs, I'd cache aggressively and only call the LLM when coverage drops or new categories appear.

### "When would you trust the agent's output vs override it?"

**Trust**: routine classifications (elevator = Elevator, confidence 1.0), statistical anomaly detection (null rates, outliers). **Review**: ambiguous mappings ("indoor air quality" → HVAC vs Health & Environmental), edge cases (categories with <5 occurrences), gold layer design suggestions. Confidence scores triage what needs human attention.

### "How would you evaluate if an agent is good enough?"

An agent evaluation harness — a test set of known-good rows with expected classifications. Compare agent output against ground truth. Metrics: accuracy, recall, false positive rate, latency, cost per call. Gate on accuracy > 95% before promoting to production. This is a "good to have" from the assignment.

### "What's the biggest weakness of your solution?"

Three things: (1) full reload doesn't scale — need incremental for production volumes, (2) silver layer processes rows one at a time — need batching for performance, (3) idempotency verification only proves bronze, not full silver/gold re-runs.

### "What would you do differently with unlimited time?"

Add dbt for transformation testing and documentation, implement an agent evaluation harness, add proper incremental loads with watermark columns, set up observability (row count drift, null rate trends, agent suggestion queue depth), and add human-in-the-loop approval gates for high-risk agent suggestions.

### "If you had to choose one agent to keep, which one?"

Semantic Classification. Data quality profiling I can write myself in 15 minutes. But normalizing 98 free-text categories into 15 business groups — that's where LLMs provide a genuine force multiplier. The difference between manual regex/similarity matching and semantic understanding ("vertical transport" = elevator) is the difference between hours and seconds.

### "Your README says 104 entries but earlier versions said 98. What happened?"

The initial analysis captured 98 distinct category values. But when I validated against the actual silver output, I found 56 unmapped categories — real variants like `ac`, `air conditioning`, and long descriptions mis-loaded into the category field. I expanded the mapping to 104 entries and added a 52-keyword fallback. The lesson: always validate analysis assumptions against actual pipeline output.

### "You removed an is_duplicate column. Why was it there originally?"

It was a vestige of an earlier design — originally intended to load duplicates and flag them rather than skip. I chose to skip them to keep silver clean, making the column always-False. Dead columns are technical debt — I removed it from the DDL and inserts.

### "What's the difference between deterministic and LLM-assisted agent modes?"

**Deterministic**: rules generated from statistical profiling with hardcoded thresholds and pre-built mappings. Runs instantly, costs $0, produces consistent output. **LLM-assisted**: sends profile data to an LLM with a structured prompt asking for rules, justifications, and implementation. More flexible, catches edge cases deterministic rules miss, but costs API credits. **prompt_only**: outputs the prompt without calling the API — for the human-in-the-loop workflow: AI proposes, human reviews, code executes.

### "What changes at 100x scale?"

- **Storage**: Partition silver by `created_at` month. Add composite indexes. Bronze lands in object storage (S3/MinIO) as Parquet, not PostgreSQL.
- **Orchestration**: Airflow/Dagster DAG. Bronze hourly, silver after bronze, gold after silver. dbt for transformations with built-in testing.
- **Ingestion**: COPY protocol instead of row-by-row INSERT. executemany for silver loads.
- **Agents**: Async batch processing. Cache LLM results aggressively. Add agent evaluation harness. Cost monitoring per run.
- **Observability**: Row count drift detection, null rate trends, agent suggestion queue depth, SLA for pipeline freshness (bronze within 5 min, silver within 10 min).

---

## Project Structure

```
.
├── docker-compose.yml         # PostgreSQL 16 (Alpine)
├── requirements.txt           # psycopg2-binary, python-dateutil, pandas
├── Makefile                   # make run / make psql / make clean
├── README.md                  # Architecture + agent assessment + scale + how-to-run
├── verify.py                  # SQLite verification harness (zero deps)
├── data/
│   └── raw_tickets.csv        # Symlink to original dataset (read-only)
├── src/
│   ├── config.py              # Configuration, paths, DB settings
│   ├── db.py                  # Connection management, schema DDL
│   ├── categories.py          # ★ Single source of truth — mapping, keywords, classifiers
│   ├── main.py                # Orchestrator — entry point
│   ├── pipeline/
│   │   ├── bronze.py          # Bronze: raw ingestion + lineage
│   │   ├── silver.py          # Silver: cleanse, type, dedup, validate
│   │   └── gold.py            # Gold: 3 aggregation models
│   └── agents/
│       ├── data_quality.py    # Agent B: profile + propose cleaning rules
│       └── semantic_classify.py  # Agent C: normalize 104 → 15 categories
└── agent_outputs/             # Agent outputs (gitignored, generated at runtime)
```

---

## Quick Reference — Key Commands

```bash
# One-command pipeline
make run

# Verify without Docker (SQLite)
python3 verify.py

# Pipeline only, skip agents
python3 src/main.py --skip-agents

# Output LLM prompts without running
python3 src/main.py --agent-mode prompt_only

# Connect to PostgreSQL
make psql
# Then: SELECT * FROM gold.monthly_ticket_kpis;
```

---

## Key Numbers to Remember

| Metric | Value |
|--------|-------|
| CSV rows | 10,280 |
| Bronze rows | 10,280 |
| Silver rows (cleaned) | 9,435 |
| Duplicates excluded | 823 |
| Null ticket_ids excluded | 22 |
| Category mapping entries | 104 |
| Target categories | 15 |
| Gold categories (actual) | 12 |
| Monthly KPIs | 19 months |
| Buildings | 20 |
| Cleaning rules | 7 (DQ-001 through DQ-007) |
| Date formats handled | 8+ |
| Priority variants normalized | 13 → 4 tiers |
| Agent count | 2 (built) + 2 (intentionally skipped) |
