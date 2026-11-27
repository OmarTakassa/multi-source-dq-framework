from __future__ import annotations
import re
from datetime import date

PLACEHOLDERS = {"", "n/a", "na", "tbd", "null", "none", "-", "unknown"}
EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")


def validate_record_metadata(record: dict) -> list[str]:
    """Pure Python schema & metadata validator (used in unit tests and pre-flight checks)."""
    errors: list[str] = []

    name = str(record.get("full_name") or "").strip().lower()
    if name in PLACEHOLDERS or len(name) < 2:
        errors.append("Missing or placeholder full_name")

    email = str(record.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        errors.append("Missing or malformed email")

    country = str(record.get("country_code") or "").strip().upper()
    if country.lower() in PLACEHOLDERS or len(country) != 2 or not country.isalpha():
        errors.append("Invalid or placeholder country_code")

    consent = str(record.get("consent_flag") or "").strip().lower()
    if consent not in {"true", "1", "yes", "y"}:
        errors.append("Explicit user consent_flag missing or false")

    dob_raw = str(record.get("birth_date") or "").strip()
    try:
        dob = date.fromisoformat(dob_raw)
        if dob > date.today():
            errors.append("birth_date cannot be in the future")
    except ValueError:
        errors.append("Missing or unparseable birth_date")

    return errors
