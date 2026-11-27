from __future__ import annotations
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
from src.db import get_conn

FIRST_NAMES = ["Anna", "Lukas", "Elena", "Marcus", "Sofia", "David", "Clara", "Jonas", "Maya", "Felix"]
LAST_NAMES = ["Mueller", "Schmidt", "Weber", "Wagner", "Becker", "Hoffmann", "Kovacs", "Novak", "Rossi", "Bauer"]
COUNTRIES = ["AT", "DE", "HU", "CH", "IT", "CZ"]
SOURCES = ["web_portal", "partner_api", "legacy_csv"]


def generate_multi_source_batch(
    batch_id: str,
    n_clean: int = 900,
    seed: int = 42,
    save_raw_files: bool = True,
) -> tuple[list[dict], dict]:
    """
    Generates realistic multi-source registration records with known injected defects:
    - Exact duplicates across sources
    - Near-duplicates (typos in names/emails)
    - Missing or placeholder metadata ('N/A', 'TBD', null country/email/consent)
    - Process anomalies (approved_at earlier than submitted_at, future birth dates)
    Returns (records, ground_truth_summary).
    """
    rng = random.Random(seed)
    base_time = datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc)
    records: list[dict] = []

    # 1. Clean baseline records
    for i in range(n_clean):
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        source = SOURCES[i % len(SOURCES)]
        submitted = base_time + timedelta(minutes=i * 2)
        approved = submitted + timedelta(minutes=rng.randint(5, 180))
        dob = datetime(1975, 1, 1) + timedelta(days=rng.randint(0, 10500))

        records.append({
            "batch_id": batch_id,
            "source_system": source,
            "external_reg_id": f"{source[:3].upper()}-{10000 + i}",
            "full_name": f"{fn} {ln}",
            "email": f"{fn.lower()}.{ln.lower()}.{i}@example.org",
            "phone": f"+43660{rng.randint(1000000, 9999999)}",
            "birth_date": dob.strftime("%Y-%m-%d"),
            "country_code": rng.choice(COUNTRIES),
            "consent_flag": "true",
            "submitted_at": submitted.isoformat(),
            "approved_at": approved.isoformat(),
            "status": "approved",
        })

    # 2. Inject exact cross-source duplicates (40 records)
    exact_dups = []
    for src_rec in rng.sample(records[:max(1, len(records)//2)], min(40, max(1, len(records)//3))):
        dup = dict(src_rec)
        dup["source_system"] = "partner_api"
        dup["external_reg_id"] = f"DUP-{src_rec['external_reg_id']}"
        dup["email"] = dup["email"].upper()
        exact_dups.append(dup)

    # 3. Inject near-duplicates with minor typos (25 records)
    near_dups = []
    for src_rec in rng.sample(records[len(records)//2:], min(25, max(1, len(records)//4))):
        nd = dict(src_rec)
        nd["source_system"] = "legacy_csv"
        nd["external_reg_id"] = f"CSV-{src_rec['external_reg_id']}"
        nd["full_name"] = src_rec["full_name"].replace("e", "a", 1) + " "
        near_dups.append(nd)

    # 4. Inject missing/placeholder metadata (45 records)
    metadata_bad = []
    for idx in range(45):
        bad_field = idx % 3
        rec = {
            "batch_id": batch_id,
            "source_system": rng.choice(SOURCES),
            "external_reg_id": f"META-{9000 + idx}",
            "full_name": "N/A" if bad_field == 0 else f"Test User {idx}",
            "email": "" if bad_field == 1 else f"meta.user.{idx}@example.org",
            "phone": "+436601234567",
            "birth_date": "1995-05-12",
            "country_code": "TBD" if bad_field == 2 else "AT",
            "consent_flag": "false" if bad_field == 2 else "true",
            "submitted_at": base_time.isoformat(),
            "approved_at": (base_time + timedelta(minutes=15)).isoformat(),
            "status": "approved",
        }
        metadata_bad.append(rec)

    # 5. Inject process & state-transition anomalies (30 records)
    anomalies = []
    for idx in range(30):
        sub = base_time + timedelta(hours=idx)
        # Inverted timestamp: approved BEFORE submitted
        inv_app = sub - timedelta(minutes=45)
        anomalies.append({
            "batch_id": batch_id,
            "source_system": "partner_api",
            "external_reg_id": f"ANOM-{8000 + idx}",
            "full_name": f"Anomaly Case {idx}",
            "email": f"anom.case.{idx}@example.org",
            "phone": "+436609998877",
            "birth_date": "2030-01-01" if idx % 2 == 0 else "1992-08-10",
            "country_code": "AT",
            "consent_flag": "true",
            "submitted_at": sub.isoformat(),
            "approved_at": inv_app.isoformat(),
            "status": "approved",
        })

    all_records = records + exact_dups + near_dups + metadata_bad + anomalies
    rng.shuffle(all_records)

    if save_raw_files:
        raw_dir = Path("data/raw")
        raw_dir.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(all_records)
        df[df["source_system"] == "legacy_csv"].to_csv(raw_dir / f"{batch_id}_legacy.csv", index=False)
        df[df["source_system"] == "partner_api"].to_json(
            raw_dir / f"{batch_id}_partner_api.json", orient="records", indent=2
        )

    ground_truth = {
        "batch_id": batch_id,
        "total_generated": len(all_records),
        "clean_expected": n_clean,
        "injected_exact_duplicates": len(exact_dups),
        "injected_near_duplicates": len(near_dups),
        "injected_metadata_errors": len(metadata_bad),
        "injected_anomalies": len(anomalies),
        "total_injected_defects": len(exact_dups) + len(near_dups) + len(metadata_bad) + len(anomalies),
    }
    return all_records, ground_truth


def load_batch_to_postgres(records: list[dict]) -> int:
    insert_sql = """
        INSERT INTO raw_registrations (
            batch_id, source_system, external_reg_id, full_name, email,
            phone, birth_date, country_code, consent_flag,
            submitted_at, approved_at, status, raw_payload
        ) VALUES (
            %(batch_id)s, %(source_system)s, %(external_reg_id)s, %(full_name)s, %(email)s,
            %(phone)s, %(birth_date)s, %(country_code)s, %(consent_flag)s,
            %(submitted_at)s, %(approved_at)s, %(status)s, %(raw_payload)s::jsonb
        )
    """
    rows = [{**r, "raw_payload": json.dumps(r)} for r in records]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(insert_sql, rows)
    return len(rows)


if __name__ == "__main__":
    batch = "batch_2026_11_27_001"
    recs, truth = generate_multi_source_batch(batch_id=batch)
    inserted = load_batch_to_postgres(recs)
    print(f"Loaded {inserted} records into raw_registrations. Ground truth: {truth}")
