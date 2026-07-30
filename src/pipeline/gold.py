"""Gold layer: business-ready aggregations and models."""
import logging
from datetime import datetime, timezone

from src.config import SILVER_SCHEMA, SILVER_TABLE, GOLD_SCHEMA, GOLD_TABLES
from src.db import get_cursor

logger = logging.getLogger(__name__)


def build_monthly_kpis():
    """
    Gold Model 1: Monthly Ticket KPIs.

    Why this matters: Operations managers need month-over-month trends —
    are tickets increasing? Is resolution rate improving? Are costs rising?
    This is the executive dashboard view.
    """
    table = GOLD_TABLES["monthly_ticket_kpis"]
    sql = f"""
    INSERT INTO {GOLD_SCHEMA}.{table}
        (year_month, total_tickets, resolved_tickets, resolution_rate_pct,
         avg_cost, avg_resolution_days, sla_breach_pct, gold_generated_at)
    SELECT
        TO_CHAR(created_at, 'YYYY-MM') AS year_month,
        COUNT(*) AS total_tickets,
        COUNT(resolved_at) AS resolved_tickets,
        ROUND(100.0 * COUNT(resolved_at) / NULLIF(COUNT(*), 0), 2) AS resolution_rate_pct,
        ROUND(AVG(cost)::numeric, 2) AS avg_cost,
        ROUND(AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 86400)::numeric, 2)
            AS avg_resolution_days,
        ROUND(100.0 * COUNT(*) FILTER (
            WHERE sla_hours IS NOT NULL
              AND EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600 > sla_hours
        ) / NULLIF(COUNT(*) FILTER (WHERE sla_hours IS NOT NULL AND resolved_at IS NOT NULL), 0), 2)
            AS sla_breach_pct,
        NOW() AS gold_generated_at
    FROM {SILVER_SCHEMA}.{SILVER_TABLE}
    WHERE created_at IS NOT NULL
    GROUP BY year_month
    ORDER BY year_month
    ON CONFLICT (year_month) DO UPDATE SET
        total_tickets = EXCLUDED.total_tickets,
        resolved_tickets = EXCLUDED.resolved_tickets,
        resolution_rate_pct = EXCLUDED.resolution_rate_pct,
        avg_cost = EXCLUDED.avg_cost,
        avg_resolution_days = EXCLUDED.avg_resolution_days,
        sla_breach_pct = EXCLUDED.sla_breach_pct,
        gold_generated_at = NOW();
    """
    with get_cursor() as cur:
        cur.execute(sql)
        logger.info(f"Gold: {table} — upserted {cur.rowcount} rows")


def build_category_analytics():
    """
    Gold Model 2: Category Analytics.

    Why this matters: Facilities managers need to know which problem categories
    cost the most, which have the worst SLA adherence, and where to allocate
    preventive maintenance budgets.
    """
    table = GOLD_TABLES["category_analytics"]
    sql = f"""
    INSERT INTO {GOLD_SCHEMA}.{table}
        (category, total_tickets, avg_cost, avg_sla_hours,
         sla_breach_pct, top_building, gold_generated_at)
    SELECT
        category_normalized AS category,
        COUNT(*) AS total_tickets,
        ROUND(AVG(cost)::numeric, 2) AS avg_cost,
        ROUND(AVG(sla_hours)::numeric, 2) AS avg_sla_hours,
        ROUND(100.0 * COUNT(*) FILTER (
            WHERE sla_hours IS NOT NULL AND resolved_at IS NOT NULL
              AND EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600 > sla_hours
        ) / NULLIF(COUNT(*) FILTER (
            WHERE sla_hours IS NOT NULL AND resolved_at IS NOT NULL
        ), 0), 2) AS sla_breach_pct,
        MODE() WITHIN GROUP (ORDER BY building) AS top_building,
        NOW() AS gold_generated_at
    FROM {SILVER_SCHEMA}.{SILVER_TABLE}
    WHERE category_normalized IS NOT NULL
    GROUP BY category_normalized
    ON CONFLICT (category) DO UPDATE SET
        total_tickets = EXCLUDED.total_tickets,
        avg_cost = EXCLUDED.avg_cost,
        avg_sla_hours = EXCLUDED.avg_sla_hours,
        sla_breach_pct = EXCLUDED.sla_breach_pct,
        top_building = EXCLUDED.top_building,
        gold_generated_at = NOW();
    """
    with get_cursor() as cur:
        cur.execute(sql)
        logger.info(f"Gold: {table} — upserted {cur.rowcount} rows")


def build_building_health():
    """
    Gold Model 3: Building Health Scorecard.

    Why this matters: Each building/facility needs a health score.
    Which buildings have the most open tickets? Which take longest to resolve?
    This drives resource allocation and identifies systemic issues.
    """
    table = GOLD_TABLES["building_health"]
    sql = f"""
    INSERT INTO {GOLD_SCHEMA}.{table}
        (building, total_tickets, open_tickets, avg_open_age_days,
         avg_resolution_days, sla_breach_pct, avg_cost, gold_generated_at)
    SELECT
        building,
        COUNT(*) AS total_tickets,
        COUNT(*) FILTER (WHERE status NOT IN ('Resolved', 'Closed')) AS open_tickets,
        ROUND(AVG(
            EXTRACT(EPOCH FROM (NOW() - created_at)) / 86400
        ) FILTER (
            WHERE status NOT IN ('Resolved', 'Closed')
              AND created_at IS NOT NULL
        )::numeric, 2) AS avg_open_age_days,
        ROUND(AVG(
            EXTRACT(EPOCH FROM (resolved_at - created_at)) / 86400
        ) FILTER (WHERE resolved_at IS NOT NULL)::numeric, 2) AS avg_resolution_days,
        ROUND(100.0 * COUNT(*) FILTER (
            WHERE sla_hours IS NOT NULL AND resolved_at IS NOT NULL
              AND EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600 > sla_hours
        ) / NULLIF(COUNT(*) FILTER (
            WHERE sla_hours IS NOT NULL AND resolved_at IS NOT NULL
        ), 0), 2) AS sla_breach_pct,
        ROUND(AVG(cost)::numeric, 2) AS avg_cost,
        NOW() AS gold_generated_at
    FROM {SILVER_SCHEMA}.{SILVER_TABLE}
    WHERE building IS NOT NULL
    GROUP BY building
    ON CONFLICT (building) DO UPDATE SET
        total_tickets = EXCLUDED.total_tickets,
        open_tickets = EXCLUDED.open_tickets,
        avg_open_age_days = EXCLUDED.avg_open_age_days,
        avg_resolution_days = EXCLUDED.avg_resolution_days,
        sla_breach_pct = EXCLUDED.sla_breach_pct,
        avg_cost = EXCLUDED.avg_cost,
        gold_generated_at = NOW();
    """
    with get_cursor() as cur:
        cur.execute(sql)
        logger.info(f"Gold: {table} — upserted {cur.rowcount} rows")


def build_gold():
    """Run all gold layer aggregations."""
    logger.info("=== GOLD LAYER: Building aggregations ===")
    build_monthly_kpis()
    build_category_analytics()
    build_building_health()
    logger.info("Gold layer complete: 3 aggregation models built.")
