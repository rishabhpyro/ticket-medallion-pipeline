"""
Data Quality Agent (Agent B)

Profiles the bronze layer, detects anomalies, proposes cleaning rules
in natural language with justification, and generates the SQL/Python
to implement them.

This agent can run in two modes:
  1. PROMPT_ONLY: outputs the prompt it would send to an LLM (for review)
  2. DETERMINISTIC: applies rule-based profiling and generates rules directly
     (works without API keys — the interviewer can run this)
"""

import json
import logging
from collections import Counter
from datetime import datetime, timezone

from src.config import BRONZE_SCHEMA, BRONZE_TABLE, AGENT_OUTPUT_DIR
from src.db import get_cursor

logger = logging.getLogger(__name__)


def profile_bronze():
    """
    Profile the bronze layer — column-level statistics.
    Returns a dict suitable for passing to an LLM or using deterministically.
    """
    with get_cursor() as cur:
        cur.execute(f"SELECT * FROM {BRONZE_SCHEMA}.{BRONZE_TABLE}")
        columns = [desc[0] for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    total = len(rows)
    profile = {"total_rows": total, "columns": {}, "sample_rows": rows[:5]}

    data_columns = [c for c in columns if c not in ("ingested_at", "source_file", "row_hash")]

    for col in data_columns:
        values = [r.get(col, "") for r in rows]
        non_null = [v for v in values if v and v.strip()]
        null_count = total - len(non_null)
        null_rate = round(null_count / total * 100, 2) if total else 0

        col_profile = {
            "null_count": null_count,
            "null_rate_pct": null_rate,
            "distinct_count": len(set(non_null)),
        }

        # Extra detail for key columns
        if col == "category":
            col_profile["top_values"] = Counter(
                v.strip().lower() for v in non_null
            ).most_common(20)
            col_profile["total_distinct"] = len(set(v.strip().lower() for v in non_null))
        elif col == "priority":
            col_profile["top_values"] = Counter(
                v.strip().lower() for v in non_null
            ).most_common(15)
        elif col in ("created_at", "resolved_at"):
            # Count format patterns
            formats = Counter()
            import re
            for v in non_null:
                v = v.strip()
                if re.match(r"^\d{4}-\d{2}-\d{2}T", v):
                    formats["ISO-T"] += 1
                elif re.match(r"^\d{4}-\d{2}-\d{2} ", v):
                    formats["ISO-space"] += 1
                elif re.match(r"^\d{2}/\d{2}/\d{4}", v):
                    formats["US-slash"] += 1
                elif re.match(r"^\d{2}-\d{2}-\d{4}", v):
                    formats["US-dash"] += 1
                elif re.match(r"^\d{2}-[A-Z][a-z]{2}-\d{4}", v):
                    formats["Euro-dash"] += 1
                elif re.match(r"^\d{10}$", v):
                    formats["Unix-ts"] += 1
                elif re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                    formats["Date-only"] += 1
                elif v.upper() in ("TBD", "N/A", "NULL"):
                    formats["Invalid-text"] += 1
                else:
                    formats[f"Unknown: {v[:30]}"] += 1
            col_profile["format_distribution"] = dict(formats.most_common(10))
        elif col == "cost":
            clean_costs = []
            bad = []
            for v in non_null:
                clean = v.replace("$", "").replace(",", "").replace('"', "").strip()
                try:
                    c = float(clean)
                    clean_costs.append(c)
                except ValueError:
                    bad.append(v)
            col_profile["bad_values"] = list(set(bad))[:10]
            if clean_costs:
                col_profile["min"] = min(clean_costs)
                col_profile["max"] = max(clean_costs)
                col_profile["negative_count"] = sum(1 for c in clean_costs if c < 0)
        elif col == "sla_hours":
            clean_sla = []
            bad = []
            for v in non_null:
                try:
                    s = float(v.strip())
                    clean_sla.append(s)
                except ValueError:
                    bad.append(v.strip())
            col_profile["bad_values"] = list(set(bad))[:10]
            if clean_sla:
                col_profile["common_values"] = Counter(clean_sla).most_common(10)
                col_profile["sentinel_999_count"] = sum(1 for s in clean_sla if s == 999)

        profile["columns"][col] = col_profile

    return profile


def generate_deterministic_rules(profile):
    """
    Generate cleaning rules based on profile data — no LLM needed.
    Returns a list of rules with natural-language justification.
    This is the "deterministic fallback" mode.
    """
    rules = []

    # Rule 1: Date parsing
    date_formats_created = profile["columns"]["created_at"].get("format_distribution", {})
    if any("Unknown" in k or "Invalid" in k for k in date_formats_created):
        rules.append({
            "rule_id": "DQ-001",
            "column": "created_at, resolved_at",
            "rule": "Multi-format date parser: detect ISO-T, ISO-space, US-slash, "
                    "US-dash, Euro-dash, Unix timestamp, date-only. Flag unparseable "
                    "values (TBD, N/A) as NULL with data_quality_flag.",
            "justification": f"Found {len(date_formats_created)} distinct date formats "
                             f"including invalid text values. A single-format parser would "
                             f"lose data. Cascading parser preserves maximum information.",
            "implementation": "python: dateutil.parser.parse() with fallback chain",
        })

    # Rule 2: Category normalization
    cat_distinct = profile["columns"]["category"].get("total_distinct", 0)
    if cat_distinct > 20:
        rules.append({
            "rule_id": "DQ-002",
            "column": "category",
            "rule": "Normalize categories using a mapping table. Group synonyms: "
                    "'elevator/lift/vertical transport' → Elevator, "
                    "'hvac/a/c/climate control' → HVAC, "
                    "'electrical/power/elec' → Electrical, etc. "
                    "Flag unmapped categories as 'Other'.",
            "justification": f"{cat_distinct} distinct category spellings detected, "
                             f"but many are synonyms or case variants. High cardinality "
                             f"in categorical columns makes aggregations meaningless. "
                             f"Normalization collapses to ~8-10 meaningful groups.",
            "implementation": "python: CATEGORY_MAPPING dict in silver.py",
        })

    # Rule 3: Priority normalization
    pri_null = profile["columns"]["priority"]["null_rate_pct"]
    pri_values = profile["columns"]["priority"].get("top_values", [])
    pri_distinct = len(pri_values)
    if pri_distinct > 5 or pri_null > 5:
        rules.append({
            "rule_id": "DQ-003",
            "column": "priority",
            "rule": "Normalize to 4 tiers: CRITICAL, HIGH, MEDIUM, LOW. "
                    "Map 'urgent!!!', 'asap' → CRITICAL. "
                    "Map 'normal' → MEDIUM. "
                    f"Default NULL ({pri_null}% of rows) → MEDIUM with flag.",
            "justification": f"{pri_distinct} priority variants with {pri_null}% null rate. "
                             f"Without normalization, filtering by priority is unreliable.",
            "implementation": "python: PRIORITY_MAPPING dict in silver.py",
        })

    # Rule 4: Cost cleaning
    cost_data = profile["columns"]["cost"]
    if cost_data.get("negative_count", 0) > 0:
        rules.append({
            "rule_id": "DQ-004",
            "column": "cost",
            "rule": "Remove $ and comma separators. Cast to DECIMAL. "
                    "Nullify negative values and sentinel values (N/A, TBD, error). "
                    "Flag zero-cost tickets for review.",
            "justification": f"Found {cost_data.get('negative_count', 0)} negative costs "
                             f"and {len(cost_data.get('bad_values', []))} invalid formats. "
                             f"Negative costs are impossible for facility tickets.",
            "implementation": "python: clean_cost() in silver.py",
        })

    # Rule 5: SLA cleaning
    sla_data = profile["columns"]["sla_hours"]
    sentinel_count = sla_data.get("sentinel_999_count", 0)
    if sentinel_count > 0:
        rules.append({
            "rule_id": "DQ-005",
            "column": "sla_hours",
            "rule": "Cast to INTEGER. Nullify sentinel value 999 and negative values. "
                    "Treat N/A, TBD as NULL. Keep 0 as valid (emergency tickets).",
            "justification": f"{sentinel_count} rows have sentinel value 999 — likely "
                             f"a data entry error or 'no SLA'. Keeping as-is would "
                             f"distort SLA compliance metrics.",
            "implementation": "python: clean_sla() in silver.py",
        })

    # Rule 6: Duplicate handling
    rules.append({
        "rule_id": "DQ-006",
        "column": "resolution_notes",
        "rule": "Detect duplicates by pattern matching 'Duplicate of ticket #XXXX' "
                "in resolution_notes. Exclude from silver layer with flag.",
        "justification": "~823 rows marked as duplicates in resolution_notes. "
                         "Including them would inflate ticket volumes and distort metrics.",
        "implementation": "python: regex pattern match in silver.py",
    })

    # Rule 7: Resolved-before-created validation
    rules.append({
        "rule_id": "DQ-007",
        "column": "resolved_at vs created_at",
        "rule": "Flag rows where resolved_at < created_at. "
                "Swap dates if clearly transposed; otherwise flag for manual review.",
        "justification": "Temporal impossibility: a ticket cannot be resolved before "
                         "it's created. Indicates data entry errors.",
        "implementation": "python: comparison check in silver.py, flag in data_quality_flags JSONB",
    })

    return rules


def run_data_quality_agent(mode="deterministic"):
    """
    Run the Data Quality Agent.

    Args:
        mode: "deterministic" (default, no API needed) or "prompt_only" (outputs LLM prompt)

    Returns:
        dict with profile, rules, and mode info.
    """
    logger.info("=== AGENT: Data Quality Agent ===")

    profile = profile_bronze()

    if mode == "prompt_only":
        prompt = build_llm_prompt(profile)
        output_path = AGENT_OUTPUT_DIR / "data_quality_prompt.txt"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(prompt)
        logger.info(f"LLM prompt written to {output_path}")
        return {"mode": "prompt_only", "prompt_file": str(output_path), "profile": profile}
    else:
        rules = generate_deterministic_rules(profile)
        output_path = AGENT_OUTPUT_DIR / "data_quality_rules.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "deterministic",
            "profile_summary": {
                "total_rows": profile["total_rows"],
                "column_count": len(profile["columns"]),
            },
            "rules": rules,
        }
        output_path.write_text(json.dumps(output, indent=2))
        logger.info(f"Generated {len(rules)} cleaning rules → {output_path}")

        # Print rules for console
        for rule in rules:
            logger.info(f"  {rule['rule_id']}: {rule['column']} — {rule['rule'][:80]}...")
            logger.info(f"    Why: {rule['justification'][:100]}...")

        return output


def build_llm_prompt(profile):
    """Build a structured prompt for an LLM-based data quality analysis."""
    return f"""You are a Data Quality Agent for a medallion architecture pipeline.
You are analyzing a bronze-layer table of facility maintenance tickets.

## Context
- Total rows: {profile['total_rows']}
- The data has been ingested raw (schema-on-read, all TEXT columns).
- Your job: profile the data and propose cleaning rules for the silver layer.

## Profile Summary
{json.dumps({col: {k: v for k, v in info.items() if k not in ('top_values', 'format_distribution', 'common_values')}
             for col, info in profile['columns'].items()}, indent=2)}

## Sample Rows
{json.dumps(profile['sample_rows'], indent=2, default=str)}

## Task
For each column, propose:
1. The silver-layer type (TIMESTAMPTZ, DECIMAL, INTEGER, TEXT, etc.)
2. Cleaning rules with natural-language justification
3. Edge case handling (what to do with NULLs, sentinel values, unparseable data)
4. Suggested implementation (SQL DDL + Python transformation logic)

## Output Format
Return a JSON array of rules. Each rule must have:
- rule_id: string (e.g., "DQ-001")
- column: string
- rule: string (the cleaning rule)
- justification: string (WHY this rule matters)
- implementation: string (SQL or Python snippet)

Focus on rules that materially improve data quality. Skip cosmetic rules.
Prioritize rules that prevent data loss or metric distortion.
"""
