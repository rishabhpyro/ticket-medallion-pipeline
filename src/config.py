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
# These are the 98 unique raw category values found in the data.
# Used by the Semantic Classification Agent for normalization.
RAW_CATEGORIES = [
    "security", "plumbing", "pest control", "cleaning", "elevator",
    "electrical", "fire safety", "general maintenance", "janitorial",
    "network", "exterminator", "pest", "hvac", "sprinkler",
    "plumbing issue", "fire/safety", "housekeeping", "fire alarm",
    "misc", "access control", "badge/access", "maintenance",
    "water/plumbing", "water issue", "other", "vertical transport",
    "lift", "elevator/escalator", "security systems",
    "electrical systems", "it/network", "connectivity", "general",
    "it", "power", "power issue", "elec", "wifi", "it support",
    "climate control", "a/c", "lighting", "heating/cooling",
    "doors/locks", "parking", "grounds/landscaping", "structural",
    "roofing", "windows", "paint", "carpentry", "appliances",
    "signage", "furniture", "moving/relocation", "event setup",
    "vending", "kitchen equipment", "restroom supplies",
    "waste management", "recycling", "hazardous materials",
    "emergency systems", "first aid", "safety equipment",
    "surveillance", "alarm systems", "key management",
    "visitor management", "mail services", "shipping/receiving",
    "fleet services", "fuel systems", "generator", "ups/battery",
    "data center", "server room", "telecom", "audio/visual",
    "conference room equipment", "cubicle/workspace",
    "ergonomics", "indoor air quality", "temperature control",
    "humidity", "noise complaint", "odor complaint",
    "pest sighting", "wildlife", "flooding", "leak",
    "mold/mildew", "asbestos", "lead", "radon",
    "ada compliance", "inspection", "permit", "code violation",
]
