"""Silver layer: cleansing, typing, deduplication, and validation."""
import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from dateutil.parser import parse as parse_date, ParserError

from src.config import BRONZE_SCHEMA, BRONZE_TABLE, SILVER_SCHEMA, SILVER_TABLE
from src.db import get_cursor, truncate_table
from src.categories import (
    VALID_STATUSES, classify_category, normalize_priority,
)

logger = logging.getLogger(__name__)


def parse_date_safe(value: str):
    """Parse a date string using multiple strategies. Returns datetime or None."""
    if not value or not value.strip():
        return None
    val = value.strip()

    # TBD / garbage
    if val.upper() in ("TBD", "N/A", "NULL", "???"):
        return None

    # Unix timestamp (10 digits, seconds since epoch)
    if re.match(r"^\d{10}$", val):
        try:
            return datetime.fromtimestamp(int(val), tz=timezone.utc)
        except (ValueError, OSError):
            pass

    # Try dateutil (handles ISO, US slash, US dash, Euro dash, AM/PM)
    try:
        return parse_date(val, dayfirst=False, fuzzy=True)
    except (ParserError, ValueError, OverflowError):
        pass

    # Last resort: date-only
    try:
        return datetime.strptime(val[:10], "%Y-%m-%d")
    except ValueError:
        pass

    return None


def clean_cost(value: str):
    """Clean cost value. Returns Decimal or None."""
    if not value or not value.strip():
        return None
    val = value.strip()

    # Garbage values
    if val.upper() in ("TBD", "N/A", "ERROR", "NULL"):
        return None

    # Remove $ and commas
    clean = val.replace("$", "").replace(",", "").replace('"', "").strip()
    try:
        c = Decimal(clean)
        # Pass through all values; validation happens in build_silver()
        if c > 100000:  # Unreasonable for a single facility ticket
            return None
        return c
    except (InvalidOperation, ValueError):
        return None


def clean_sla(value: str):
    """Clean SLA hours. Returns int or None."""
    if not value or not value.strip():
        return None
    val = value.strip().upper()

    if val in ("N/A", "TBD", "NULL"):
        return None

    try:
        s = int(float(val))
        if s in (999, -1):  # Sentinel values
            return None
        if s < 0:  # Invalid
            return None
        return s
    except (ValueError, TypeError):
        return None


def build_silver():
    """
    Transform bronze → silver.

    - Parses dates from multiple formats
    - Normalizes categories and priorities
    - Cleans cost and SLA fields
    - Flags duplicates (by resolution_notes pattern)
    - Validates data (resolved_at >= created_at)
    - Records data quality issues in JSONB flags

    Returns:
        int: Number of rows loaded to silver.
    """
    logger.info("=== SILVER LAYER: Starting transformation ===")
    truncate_table(SILVER_SCHEMA, SILVER_TABLE)

    # Fetch all bronze rows
    with get_cursor() as cur:
        cur.execute(f"SELECT * FROM {BRONZE_SCHEMA}.{BRONZE_TABLE}")
        columns = [desc[0] for desc in cur.description]
        bronze_rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    logger.info(f"Fetched {len(bronze_rows)} rows from bronze")

    insert_sql = f"""
            INSERT INTO {SILVER_SCHEMA}.{SILVER_TABLE}
            (ticket_id, created_at, resolved_at, category_raw, category_normalized,
             priority, status, building, description, submitted_by, assigned_to,
             resolution_notes, cost, sla_hours, data_quality_flags,
             silver_processed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    stats = {
        "total": 0,
        "loaded": 0,
        "skipped_duplicate": 0,
        "skipped_null_ticket_id": 0,
        "date_parse_failures": 0,
        "cost_cleaned": 0,
        "sla_cleaned": 0,
        "priority_normalized": 0,
        "category_normalized": 0,
    }

    with get_cursor() as cur:
        for row in bronze_rows:
            stats["total"] += 1
            flags = {}

            # Skip rows with no ticket_id
            tid = (row.get("ticket_id") or "").strip()
            if not tid or tid.upper() in ("N/A", "NULL"):
                stats["skipped_null_ticket_id"] += 1
                continue

            # Skip duplicate tickets (flagged in resolution_notes)
            res_notes = (row.get("resolution_notes") or "")
            is_dup = "duplicate of ticket" in res_notes.lower()
            if is_dup:
                stats["skipped_duplicate"] += 1
                continue

            # Parse dates
            created_at = parse_date_safe(row.get("created_at", ""))
            resolved_at = parse_date_safe(row.get("resolved_at", ""))
            if not created_at:
                stats["date_parse_failures"] += 1
                flags["created_at_unparseable"] = row.get("created_at", "")
            if not resolved_at and row.get("resolved_at", "").strip():
                stats["date_parse_failures"] += 1
                flags["resolved_at_unparseable"] = row.get("resolved_at", "")

            # Validate: resolved_at >= created_at
            if created_at and resolved_at and resolved_at < created_at:
                flags["resolved_before_created"] = True

            # Normalize category (shared logic from src.categories)
            raw_cat = (row.get("category") or "").strip().lower()
            norm_cat, cat_flags = classify_category(row.get("category") or "")
            flags.update(cat_flags)
            if norm_cat and norm_cat != raw_cat:
                stats["category_normalized"] += 1

            # Normalize priority (shared logic from src.categories)
            raw_pri = (row.get("priority") or "").strip().lower()
            norm_pri, pri_flags = normalize_priority(row.get("priority") or "")
            flags.update(pri_flags)
            if norm_pri and norm_pri != raw_pri.upper():
                stats["priority_normalized"] += 1

            # Validate status
            raw_status = (row.get("status") or "").strip().lower()
            if raw_status not in VALID_STATUSES and raw_status:
                flags["unrecognized_status"] = raw_status

            # Clean cost
            cost = clean_cost(row.get("cost", ""))
            if cost is not None and cost < 0:
                flags["negative_cost"] = str(cost)
                cost = None
            if cost is not None and cost == 0:
                flags["zero_cost"] = True
            if cost is not None:
                stats["cost_cleaned"] += 1

            # Clean SLA
            sla = clean_sla(row.get("sla_hours", ""))
            if sla is not None:
                stats["sla_cleaned"] += 1

            cur.execute(insert_sql, (
                tid,
                created_at,
                resolved_at,
                raw_cat,
                norm_cat,
                norm_pri,
                raw_status.title() if raw_status else None,
                (row.get("building") or "").strip() or None,
                (row.get("description") or "").strip() or None,
                (row.get("submitted_by") or "").strip() or None,
                (row.get("assigned_to") or "").strip() or None,
                res_notes.strip() or None,
                cost,
                sla,
                json.dumps(flags) if flags else None,
                datetime.now(timezone.utc),
            ))
            stats["loaded"] += 1

    logger.info(f"Silver transformation complete.")
    logger.info(f"  Total bronze rows:     {stats['total']}")
    logger.info(f"  Loaded to silver:      {stats['loaded']}")
    logger.info(f"  Skipped (null id):     {stats['skipped_null_ticket_id']}")
    logger.info(f"  Skipped (duplicates):  {stats['skipped_duplicate']}")
    logger.info(f"  Date parse failures:   {stats['date_parse_failures']}")
    logger.info(f"  Categories normalized: {stats['category_normalized']}")
    logger.info(f"  Priorities normalized: {stats['priority_normalized']}")
    return stats["loaded"]
