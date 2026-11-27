from __future__ import annotations
import json
from rapidfuzz import fuzz
from src.db import get_conn


def detect_fuzzy_duplicates(batch_id: str, similarity_threshold: float = 88.0) -> int:
    """
    Detects near-duplicate records remaining in stg_registrations after exact hash dedup.
    Blocks candidates by (birth_date_parsed, country_code_norm) and scores full_name + email similarity.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.stg_id, s.raw_id, s.source_system, s.full_name_norm,
                       s.email_norm, s.birth_date_parsed, s.country_code_norm,
                       r.raw_payload
                FROM stg_registrations s
                JOIN raw_registrations r ON r.raw_id = s.raw_id
                WHERE s.batch_id = %s AND s.is_valid = TRUE
                ORDER BY s.stg_id ASC
                """,
                (batch_id,),
            )
            candidates = cur.fetchall()

            # Group by blocking key (birth_date, country_code) to avoid O(N^2) full scans
            blocks: dict[tuple, list[dict]] = {}
            for row in candidates:
                key = (row["birth_date_parsed"], row["country_code_norm"])
                blocks.setdefault(key, []).append(row)

            quarantined_rows = []
            flagged_stg_ids = []

            for group in blocks.values():
                if len(group) < 2:
                    continue
                for i in range(len(group)):
                    if group[i]["stg_id"] in flagged_stg_ids:
                        continue
                    for j in range(i + 1, len(group)):
                        cand = group[j]
                        if cand["stg_id"] in flagged_stg_ids:
                            continue
                        name_score = fuzz.token_sort_ratio(
                            group[i]["full_name_norm"], cand["full_name_norm"]
                        )
                        email_score = fuzz.ratio(
                            group[i]["email_norm"], cand["email_norm"]
                        )
                        combined = 0.6 * name_score + 0.4 * email_score
                        if combined >= similarity_threshold:
                            flagged_stg_ids.append(cand["stg_id"])
                            quarantined_rows.append(
                                (
                                    cand["raw_id"],
                                    batch_id,
                                    cand["source_system"],
                                    "DUP_FUZZY_002",
                                    "WARNING",
                                    f"Fuzzy duplicate (score={combined:.1f}%) matching stg_id={group[i]['stg_id']}",
                                    json.dumps(cand["raw_payload"]),
                                )
                            )

            if quarantined_rows:
                cur.executemany(
                    """
                    INSERT INTO quarantine_records (
                        raw_id, batch_id, source_system, rule_id, severity, failure_reason, raw_payload
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    quarantined_rows,
                )
                cur.execute(
                    "UPDATE stg_registrations SET is_valid = FALSE WHERE stg_id = ANY(%s)",
                    (flagged_stg_ids,),
                )

            return len(quarantined_rows)
