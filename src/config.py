"""Central configuration for the medallion pipeline."""
import os
from pathlib import Path

# --- Paths ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_CSV = DATA_DIR / "raw_tickets.csv"
AGENT_OUTPUT_DIR = PROJECT_ROOT / "agent_outputs"

# --- PostgreSQL ---
DB_CONFIG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": int(os.getenv("PGPORT", 5432)),
    "dbname": os.getenv("PGDATABASE", "medallion"),
    "user": os.getenv("PGUSER", "medallion"),
    "password": os.getenv("PGPASSWORD", "medallion"),
}

# --- Schema names (medallion layers) ---
BRONZE_SCHEMA = "bronze"
SILVER_SCHEMA = "silver"
GOLD_SCHEMA = "gold"

# --- Table names ---
BRONZE_TABLE = "raw_tickets"
SILVER_TABLE = "tickets_cleaned"
GOLD_TABLES = {
    "monthly_ticket_kpis": "monthly_ticket_kpis",
    "category_analytics": "category_analytics",
    "building_health": "building_health_scorecard",
}

# --- Source file metadata ---
SOURCE_FILE = str(RAW_CSV)

# --- Agent configuration ---
# Dynamically extracted from the CSV at import time so it never goes stale.
# Used by the Semantic Classification Agent for input reporting.
_RAW_CATEGORIES_CACHE = None

def get_raw_categories():
    """Lazily load distinct category values from the CSV. Cached after first call."""
    global _RAW_CATEGORIES_CACHE
    if _RAW_CATEGORIES_CACHE is not None:
        return _RAW_CATEGORIES_CACHE
    import csv
    try:
        with open(RAW_CSV, "r") as f:
            rows = list(csv.DictReader(f))
        _RAW_CATEGORIES_CACHE = sorted(set(
            r.get("category", "").strip()
            for r in rows
            if r.get("category", "").strip()
        ))
    except Exception:
        _RAW_CATEGORIES_CACHE = []
    return _RAW_CATEGORIES_CACHE

# Backward-compatible alias for code that imports RAW_CATEGORIES directly
RAW_CATEGORIES = get_raw_categories()
