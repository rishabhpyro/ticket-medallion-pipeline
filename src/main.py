#!/usr/bin/env python3
"""
Medallion Pipeline Orchestrator

Runs the full bronze → silver → gold pipeline with AI agent assistance.
Idempotent — safe to run multiple times.
Single entry point: python src/main.py

Usage:
    python src/main.py                    # Run full pipeline (deterministic agent mode)
    python src/main.py --agent-mode prompt_only  # Output LLM prompts without running
    python src/main.py --skip-agents      # Run pipeline only, skip agent analysis
    python src/main.py --bronze-only      # Only run bronze ingestion
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure src/ is on the path when run from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import init_db
from src.pipeline.bronze import ingest_bronze
from src.pipeline.silver import build_silver
from src.pipeline.gold import build_gold
from src.agents.data_quality import run_data_quality_agent
from src.agents.semantic_classify import run_semantic_classification_agent


def setup_logging():
    """Configure structured logging for the pipeline."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-7s] %(name)-25s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Medallion Pipeline: Bronze → Silver → Gold with AI Agents"
    )
    parser.add_argument(
        "--agent-mode",
        choices=["deterministic", "prompt_only"],
        default="deterministic",
        help="Agent execution mode (default: deterministic)",
    )
    parser.add_argument(
        "--skip-agents",
        action="store_true",
        help="Skip all AI agent analysis, run pipeline only",
    )
    parser.add_argument(
        "--bronze-only",
        action="store_true",
        help="Run only bronze ingestion, skip silver/gold/agents",
    )
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("main")
    logger.info("=" * 60)
    logger.info("MEDALLION PIPELINE — Facility Ticket Data")
    logger.info("=" * 60)

    # ── Initialize database ──
    logger.info("Step 0: Initializing database schemas...")
    init_db()

    # ── Bronze Layer ──
    logger.info("")
    bronze_count = ingest_bronze()
    logger.info(f"✓ Bronze complete: {bronze_count} rows ingested")

    if args.bronze_only:
        logger.info("--bronze-only flag set. Pipeline stopped after bronze.")
        return

    # ── Agent Analysis (runs on bronze data before silver transformation) ──
    if not args.skip_agents:
        logger.info("")
        logger.info("─" * 40)
        logger.info("AGENT ANALYSIS PHASE")
        logger.info("─" * 40)

        logger.info("")
        dq_result = run_data_quality_agent(mode=args.agent_mode)
        logger.info(f"✓ Data Quality Agent: {dq_result.get('mode', 'unknown')} mode")

        logger.info("")
        sc_result = run_semantic_classification_agent(mode=args.agent_mode)
        if sc_result.get("mode") != "prompt_only":
            logger.info(
                f"✓ Semantic Classification Agent: "
                f"{sc_result.get('coverage_pct', 0)}% coverage "
                f"({sc_result.get('mapped_categories', 0)}/{sc_result.get('input_categories', 0)} categories)"
            )
        else:
            logger.info(f"✓ Semantic Classification Agent: prompt written")
    else:
        logger.info("--skip-agents flag set. Skipping agent analysis.")

    # ── Silver Layer ──
    logger.info("")
    silver_count = build_silver()
    logger.info(f"✓ Silver complete: {silver_count} clean rows loaded")

    # ── Gold Layer ──
    logger.info("")
    build_gold()
    logger.info("✓ Gold complete: 3 aggregation models built")

    # ── Summary ──
    logger.info("")
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"  Bronze: {bronze_count} raw rows with lineage metadata")
    logger.info(f"  Silver: {silver_count} cleansed, typed, validated rows")
    logger.info(f"  Gold:   3 aggregation tables (KPIs, Categories, Buildings)")
    if not args.skip_agents:
        logger.info(f"  Agents: Data Quality + Semantic Classification ({args.agent_mode})")
    logger.info("=" * 60)
    logger.info("To query results:")
    logger.info("  docker exec -it medallion-pg psql -U medallion")
    logger.info("  SELECT * FROM gold.monthly_ticket_kpis;")
    logger.info("  SELECT * FROM gold.category_analytics;")
    logger.info("  SELECT * FROM gold.building_health_scorecard;")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
