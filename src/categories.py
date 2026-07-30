"""
Shared category normalization — single source of truth.

Every module that needs category mapping, keyword fallback, or garbage
detection imports from here. No copies, no drift.
"""

# ── Explicit category mapping (104 raw → 15 normalized) ──────────
CATEGORY_MAPPING = {
    # Elevator / Vertical Transport
    "elevator": "Elevator",
    "elevator/escalator": "Elevator",
    "lift": "Elevator",
    "vertical transport": "Elevator",
    # Electrical / Power
    "electrical": "Electrical",
    "electrical systems": "Electrical",
    "elec": "Electrical",
    "power": "Electrical",
    "power issue": "Electrical",
    "lighting": "Electrical",
    "generator": "Electrical",
    "ups/battery": "Electrical",
    # HVAC / Climate (13 variants found in actual CSV)
    "hvac": "HVAC",
    "a/c": "HVAC",
    "ac": "HVAC",
    "air conditioning": "HVAC",
    "climate control": "HVAC",
    "cold": "HVAC",
    "heating cooling": "HVAC",
    "heating/cooling": "HVAC",
    "hvac system": "HVAC",
    "humidity": "HVAC",
    "indoor air quality": "HVAC",
    "temperature control": "HVAC",
    # Plumbing / Water
    "plumbing": "Plumbing",
    "plumbing issue": "Plumbing",
    "water/plumbing": "Plumbing",
    "water issue": "Plumbing",
    "flooding": "Plumbing",
    "leak": "Plumbing",
    # Fire / Safety
    "fire safety": "Fire & Safety",
    "fire/safety": "Fire & Safety",
    "fire alarm": "Fire & Safety",
    "sprinkler": "Fire & Safety",
    "emergency systems": "Fire & Safety",
    "safety equipment": "Fire & Safety",
    "first aid": "Fire & Safety",
    # Pest Control
    "pest control": "Pest Control",
    "pest": "Pest Control",
    "exterminator": "Pest Control",
    "pest sighting": "Pest Control",
    "wildlife": "Pest Control",
    # Cleaning / Janitorial
    "cleaning": "Cleaning",
    "janitorial": "Cleaning",
    "housekeeping": "Cleaning",
    "waste management": "Cleaning",
    "recycling": "Cleaning",
    "restroom supplies": "Cleaning",
    # Security / Access
    "security": "Security",
    "security systems": "Security",
    "badge/access": "Security",
    "access control": "Security",
    "surveillance": "Security",
    "alarm systems": "Security",
    "key management": "Security",
    "doors/locks": "Security",
    "visitor management": "Security",
    # IT & Network
    "network": "IT & Network",
    "it/network": "IT & Network",
    "it": "IT & Network",
    "it support": "IT & Network",
    "connectivity": "IT & Network",
    "wifi": "IT & Network",
    "telecom": "IT & Network",
    "audio/visual": "IT & Network",
    "conference room equipment": "IT & Network",
    "data center": "IT & Network",
    "server room": "IT & Network",
    # General / Maintenance
    "general maintenance": "General Maintenance",
    "maintenance": "General Maintenance",
    "general": "General Maintenance",
    # Facilities / Building
    "structural": "Facilities",
    "roofing": "Facilities",
    "windows": "Facilities",
    "paint": "Facilities",
    "carpentry": "Facilities",
    "grounds/landscaping": "Facilities",
    "parking": "Facilities",
    "signage": "Facilities",
    "furniture": "Facilities",
    "appliances": "Facilities",
    "kitchen equipment": "Facilities",
    "vending": "Facilities",
    "cubicle/workspace": "Facilities",
    "ergonomics": "Facilities",
    "moving/relocation": "Facilities",
    "event setup": "Facilities",
    # Fleet / Logistics
    "fleet services": "Fleet & Logistics",
    "fuel systems": "Fleet & Logistics",
    "shipping/receiving": "Fleet & Logistics",
    "mail services": "Fleet & Logistics",
    # Health / Environmental
    "mold/mildew": "Health & Environmental",
    "asbestos": "Health & Environmental",
    "lead": "Health & Environmental",
    "radon": "Health & Environmental",
    "hazardous materials": "Health & Environmental",
    "noise complaint": "Health & Environmental",
    "odor complaint": "Health & Environmental",
    # Compliance
    "ada compliance": "Compliance",
    "inspection": "Compliance",
    "permit": "Compliance",
    "code violation": "Compliance",
    # Misc / Catch-all
    "misc": "Other",
    "other": "Other",
}

# ── Known garbage values — nullify these, don't title-case ──────
GARBAGE_CATEGORIES = {
    "???", "asdf", "delete me", "test", "null", "",
    "n/a", "none", "tbd", "unknown",
}

# ── Keyword-based fallback for mis-categorized long descriptions ─
CATEGORY_KEYWORDS = [
    ("elevator", "Elevator"),
    ("lift", "Elevator"),
    ("toilet", "Plumbing"),
    ("faucet", "Plumbing"),
    ("pipe burst", "Plumbing"),
    ("water leak", "Plumbing"),
    ("hot water", "Plumbing"),
    ("overflowing", "Plumbing"),
    ("leak", "Plumbing"),
    ("plumbing", "Plumbing"),
    ("ac unit", "HVAC"),
    ("thermo", "HVAC"),
    ("temperature", "HVAC"),
    ("hvac", "HVAC"),
    ("cooling", "HVAC"),
    ("heating", "HVAC"),
    ("unit", "HVAC"),
    ("cycling", "HVAC"),
    ("breaker", "Electrical"),
    ("outlet", "Electrical"),
    ("electrical", "Electrical"),
    ("power", "Electrical"),
    ("fire extinguisher", "Fire & Safety"),
    ("smoke detector", "Fire & Safety"),
    ("emergency exit", "Fire & Safety"),
    ("sprinkler", "Fire & Safety"),
    ("security camera", "Security"),
    ("access card", "Security"),
    ("badge", "Security"),
    ("door", "Security"),
    ("lock", "Security"),
    ("wifi", "IT & Network"),
    ("network", "IT & Network"),
    ("vpn", "IT & Network"),
    ("outage", "IT & Network"),
    ("printer", "IT & Network"),
    ("desk", "Facilities"),
    ("furniture", "Facilities"),
    ("window", "Facilities"),
    ("chair", "Facilities"),
    ("restroom", "Cleaning"),
    ("cleaning", "Cleaning"),
    ("janitor", "Cleaning"),
    ("bird", "Pest Control"),
    ("bugs", "Pest Control"),
    ("wasp", "Pest Control"),
    ("pest", "Pest Control"),
    ("rodent", "Pest Control"),
    ("mold", "Health & Environmental"),
    ("asbestos", "Health & Environmental"),
    ("inspection", "Compliance"),
    ("wheelchair", "Compliance"),
    ("ada", "Compliance"),
]

# ── Priority normalization ──────────────────────────────────────
PRIORITY_MAPPING = {
    "critical": "CRITICAL", "crit": "CRITICAL", "urgent!!!": "CRITICAL",
    "high": "HIGH", "hi": "HIGH", "asap": "HIGH",
    "medium": "MEDIUM", "med": "MEDIUM", "normal": "MEDIUM",
    "low": "LOW", "lo": "LOW",
}

# ── Valid statuses ──────────────────────────────────────────────
VALID_STATUSES = {
    "open", "in progress", "pending vendor", "escalated",
    "resolved", "closed",
}

# ── Number of distinct raw categories the mapping was built from ─
RAW_CATEGORY_COUNT = 104  # number of entries in CATEGORY_MAPPING


def classify_category(raw: str):
    """
    Classify a raw category string using mapping → keyword fallback → garbage check.

    Returns:
        (normalized_category: str | None, flags: dict)
    """
    flags = {}
    val = (raw or "").strip().lower()

    if not val:
        return None, flags

    # 1. Exact match in mapping
    norm = CATEGORY_MAPPING.get(val)
    if norm:
        return norm, flags

    # 2. Keyword-based fallback for long descriptions
    for keyword, target in CATEGORY_KEYWORDS:
        if keyword in val:
            flags["keyword_classified"] = keyword
            return target, flags

    # 3. Garbage check — nullify, don't title-case
    if val in GARBAGE_CATEGORIES:
        flags["garbage_category"] = raw.strip()
        return None, flags

    # 4. Truly unclassifiable — title-case as last resort, with flag
    flags["unclassified_category"] = raw.strip()
    return val.title(), flags


def normalize_priority(raw: str):
    """Normalize a priority string. Returns (normalized: str | None, flags: dict)."""
    flags = {}
    val = (raw or "").strip().lower()
    if not val:
        return None, flags
    norm = PRIORITY_MAPPING.get(val)
    if norm:
        return norm, flags
    # Unknown priority — default to MEDIUM
    flags["unrecognized_priority"] = raw.strip()
    return "MEDIUM", flags
