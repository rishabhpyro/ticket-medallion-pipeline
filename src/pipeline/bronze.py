"""Bronze layer: raw ingestion with lineage metadata."""
import csv
import hashlib
import logging
from datetime import datetime, timezone

from src.config import RAW_CSV, SOURCE_FILE, BRONZE_SCHEMA, BRONZE_TABLE
from src.db import get_cursor, truncate_table

logger = logging.getLogger(__name__)


def compute_row_hash(row: dict) -> str:
    """Compute a deterministic SHA256 hash of a row for dedup tracking."""
    canonical = "|".join(f"{k}={row.get(k, '')}" for k in sorted(row.keys()))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ingest_bronze():
    """
    Ingest raw_tickets.csv into the bronze layer.

    - Reads CSV as-is (schema-on-read: all TEXT).
    - Adds lineage columns: ingested_at, source_file, row_hash.
    - Idempotent: truncates bronze table before full reload.

    Returns:
        int: Number of rows ingested.
    """
    logger.info("=== BRONZE LAYER: Starting ingestion ===")
    truncate_table(BRONZE_SCHEMA, BRONZE_TABLE)

    # Read CSV
    with open(RAW_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    logger.info(f"Read {len(rows)} rows from {RAW_CSV}")
    ingested_at = datetime.now(timezone.utc)

    insert_sql = f"""
        INSERT INTO {BRONZE_SCHEMA}.{BRONZE_TABLE}
            (ticket_id, created_at, resolved_at, category, priority,
             status, building, description, submitted_by, assigned_to,
             resolution_notes, cost, sla_hours,
             ingested_at, source_file, row_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s)
    """

    count = 0
    with get_cursor() as cur:
        for row in rows:
            row_hash = compute_row_hash(row)
            cur.execute(insert_sql, (
                row.get("ticket_id", ""),
                row.get("created_at", ""),
                row.get("resolved_at", ""),
                row.get("category", ""),
                row.get("priority", ""),
                row.get("status", ""),
                row.get("building", ""),
                row.get("description", ""),
                row.get("submitted_by", ""),
                row.get("assigned_to", ""),
                row.get("resolution_notes", ""),
                row.get("cost", ""),
                row.get("sla_hours", ""),
                ingested_at,
                SOURCE_FILE,
                row_hash,
            ))
            count += 1

    logger.info(f"Bronze ingestion complete: {count} rows loaded.")
    logger.info(f"Lineage: source={SOURCE_FILE}, ingested_at={ingested_at.isoformat()}")
    return count
