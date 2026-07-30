"""PostgreSQL connection and schema management utilities."""
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
import logging
from src.config import DB_CONFIG, BRONZE_SCHEMA, SILVER_SCHEMA, GOLD_SCHEMA

logger = logging.getLogger(__name__)


def get_connection():
    """Return a new psycopg2 connection."""
    return psycopg2.connect(**DB_CONFIG)


@contextmanager
def get_cursor(commit=True):
    """Context manager for a database cursor with auto-commit."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def create_schemas():
    """Create medallion schemas if they don't exist."""
    with get_cursor() as cur:
        for schema in [BRONZE_SCHEMA, SILVER_SCHEMA, GOLD_SCHEMA]:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            logger.info(f"Schema ensured: {schema}")


def create_bronze_table():
    """Create the bronze raw_tickets table (schema-on-read: all TEXT)."""
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {BRONZE_SCHEMA}.raw_tickets (
        ticket_id          TEXT,
        created_at         TEXT,
        resolved_at        TEXT,
        category           TEXT,
        priority           TEXT,
        status             TEXT,
        building           TEXT,
        description        TEXT,
        submitted_by       TEXT,
        assigned_to        TEXT,
        resolution_notes   TEXT,
        cost               TEXT,
        sla_hours          TEXT,
        -- lineage metadata
        ingested_at        TIMESTAMPTZ DEFAULT NOW(),
        source_file        TEXT,
        row_hash           TEXT
    );
    """
    with get_cursor() as cur:
        cur.execute(ddl)
        logger.info(f"Bronze table created/verified: {BRONZE_SCHEMA}.raw_tickets")


def create_silver_table():
    """Create the silver tickets_cleaned table with proper types."""
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {SILVER_SCHEMA}.tickets_cleaned (
        ticket_id          TEXT PRIMARY KEY,
        created_at         TIMESTAMPTZ,
        resolved_at        TIMESTAMPTZ,
        category_raw       TEXT,
        category_normalized TEXT,
        priority           TEXT,
        status             TEXT,
        building           TEXT,
        description        TEXT,
        submitted_by       TEXT,
        assigned_to        TEXT,
        resolution_notes   TEXT,
        cost               DECIMAL(12,2),
        sla_hours          INTEGER,
        is_duplicate       BOOLEAN DEFAULT FALSE,
        data_quality_flags JSONB DEFAULT '{{}}',
        silver_processed_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    with get_cursor() as cur:
        cur.execute(ddl)
        logger.info(f"Silver table created/verified: {SILVER_SCHEMA}.tickets_cleaned")


def create_gold_tables():
    """Create gold aggregation tables."""
    monthly_kpis = f"""
    CREATE TABLE IF NOT EXISTS {GOLD_SCHEMA}.monthly_ticket_kpis (
        year_month          TEXT PRIMARY KEY,
        total_tickets       INTEGER,
        resolved_tickets    INTEGER,
        resolution_rate_pct DECIMAL(5,2),
        avg_cost            DECIMAL(12,2),
        avg_resolution_days DECIMAL(8,2),
        sla_breach_pct      DECIMAL(5,2),
        gold_generated_at   TIMESTAMPTZ DEFAULT NOW()
    );
    """
    category_analytics = f"""
    CREATE TABLE IF NOT EXISTS {GOLD_SCHEMA}.category_analytics (
        category            TEXT PRIMARY KEY,
        total_tickets       INTEGER,
        avg_cost            DECIMAL(12,2),
        avg_sla_hours       DECIMAL(8,2),
        sla_breach_pct      DECIMAL(5,2),
        top_building        TEXT,
        gold_generated_at   TIMESTAMPTZ DEFAULT NOW()
    );
    """
    building_health = f"""
    CREATE TABLE IF NOT EXISTS {GOLD_SCHEMA}.building_health_scorecard (
        building            TEXT PRIMARY KEY,
        total_tickets       INTEGER,
        open_tickets        INTEGER,
        avg_open_age_days   DECIMAL(8,2),
        avg_resolution_days DECIMAL(8,2),
        sla_breach_pct      DECIMAL(5,2),
        avg_cost            DECIMAL(12,2),
        gold_generated_at   TIMESTAMPTZ DEFAULT NOW()
    );
    """
    with get_cursor() as cur:
        cur.execute(monthly_kpis)
        cur.execute(category_analytics)
        cur.execute(building_health)
        logger.info(f"Gold tables created/verified in schema: {GOLD_SCHEMA}")


def truncate_table(schema, table):
    """Idempotency helper: truncate a table before full reload."""
    with get_cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {schema}.{table} RESTART IDENTITY CASCADE")
        logger.info(f"Truncated: {schema}.{table}")


def init_db():
    """Initialize all schemas and tables."""
    logger.info("Initializing database...")
    create_schemas()
    create_bronze_table()
    create_silver_table()
    create_gold_tables()
    logger.info("Database initialization complete.")
