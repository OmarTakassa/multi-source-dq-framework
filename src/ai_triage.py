from __future__ import annotations
import json
from src.config import settings


def generate_incident_summary(
    batch_id: str,
    breakdown: list[dict],
    volume_report: dict,
    sample_failures: list[dict],
) -> str:
    """
    Produces a human-readable root-cause triage digest from deterministic DQ logs.
    Uses OpenAI when OPENAI_API_KEY is configured; otherwise generates a deterministic summary.
    """
    payload = {
        "batch_id": batch_id,
        "rule_breakdown": breakdown,
        "volume_report": volume_report,
        "sample_failures": sample_failures[:5],
    }

    if settings.openai_api_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.openai_api_key)
            resp = client.chat.completions.create(
                model="gpt-6-luna",
                messages=[
                    {
                        "role": "developer",
                        "content": (
                            "You are a senior Data Reliability Engineer. Summarize the data quality "
                            "incident metrics concisely in 3 bullet points: top failing source, "
                            "dominant defect pattern, and recommended upstream fix."
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload, default=str)},
                ],
                temperature=0.2,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            return f"[AI Triage Fallback - API error: {exc}]\n" + _deterministic_digest(payload)

    return _deterministic_digest(payload)


def _deterministic_digest(payload: dict) -> str:
    breakdown = payload.get("rule_breakdown", [])
    if not breakdown:
        return f"Batch {payload['batch_id']}: All records passed validation with zero quarantined issues."

    top_rule = max(breakdown, key=lambda r: r["issue_count"])
    lines = [
        f"Batch {payload['batch_id']} Triage Digest:",
        f"- Dominant Defect: {top_rule['rule_id']} ({top_rule['issue_count']} records) on source '{top_rule['source_system']}'.",
    ]
    for row in breakdown:
        lines.append(
            f"  * [{row['source_system']}] {row['rule_id']}: {row['issue_count']} quarantined"
        )
    if payload.get("volume_report", {}).get("has_volume_anomaly"):
        lines.append(f"- Volume Anomaly Alert: {payload['volume_report']['volume_alerts']}")
    return "\n".join(lines)
