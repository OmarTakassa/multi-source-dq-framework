from __future__ import annotations
import numpy as np
from src.db import get_conn


def check_batch_volume_anomaly(batch_id: str, mad_threshold: float = 3.5) -> dict:
    """
    Compares current batch volume per source_system against historical runs using
    Median Absolute Deviation (MAD) modified z-scores to detect silent outages or spikes.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_system, COUNT(*) AS cnt
                FROM raw_registrations
                WHERE batch_id = %s
                GROUP BY source_system
                """,
                (batch_id,),
            )
            current_counts = {r["source_system"]: r["cnt"] for r in cur.fetchall()}

            cur.execute(
                """
                SELECT source_system, batch_id, COUNT(*) AS cnt
                FROM raw_registrations
                WHERE batch_id <> %s
                GROUP BY source_system, batch_id
                """,
                (batch_id,),
            )
            history: dict[str, list[int]] = {}
            for row in cur.fetchall():
                history.setdefault(row["source_system"], []).append(row["cnt"])

    alerts = []
    for source, count in current_counts.items():
        past = history.get(source, [])
        if len(past) < 3:
            continue
        arr = np.array(past, dtype=float)
        median = float(np.median(arr))
        mad = float(np.median(np.abs(arr - median)))
        if mad == 0:
            continue
        modified_z = 0.6745 * abs(count - median) / mad
        if modified_z > mad_threshold:
            alerts.append(
                {
                    "source_system": source,
                    "current_count": count,
                    "historical_median": median,
                    "modified_z_score": round(modified_z, 2),
                }
            )

    return {
        "batch_id": batch_id,
        "source_counts": current_counts,
        "volume_alerts": alerts,
        "has_volume_anomaly": len(alerts) > 0,
    }
