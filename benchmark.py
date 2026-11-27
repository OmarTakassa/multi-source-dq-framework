from __future__ import annotations
import json
from pathlib import Path
from src.db import get_conn
from src.ingest import generate_multi_source_batch, load_batch_to_postgres
from src.pipeline import run_validation_pipeline


def run_benchmark(batch_id: str = "benchmark_v1", n_clean: int = 1800) -> dict:
    # Reset tables for a clean, reproducible benchmark measurement
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE TABLE
                    dim_registrations_clean,
                    quarantine_records,
                    stg_registrations,
                    raw_registrations,
                    dq_validation_runs
                RESTART IDENTITY CASCADE;
                """
            )

    records, truth = generate_multi_source_batch(
        batch_id=batch_id, n_clean=n_clean, seed=2026, save_raw_files=True
    )
    load_batch_to_postgres(records)
    result = run_validation_pipeline(batch_id=batch_id)

    injected = truth["total_injected_defects"]
    caught = result["total_quarantined"]
    escaped = max(0, injected - caught)

    unvalidated_error_rate = round((injected / truth["total_generated"]) * 100, 2)
    post_validation_error_rate = round((escaped / max(1, result["total_passed"])) * 100, 2)
    defect_detection_rate = round((caught / injected) * 100, 2) if injected else 100.0
    error_reduction_pct = round(
        ((unvalidated_error_rate - post_validation_error_rate) / unvalidated_error_rate) * 100, 2
    )

    report = {
        "benchmark_batch": batch_id,
        "total_records_ingested": truth["total_generated"],
        "ground_truth_clean": truth["clean_expected"],
        "ground_truth_injected_defects": injected,
        "defects_quarantined_by_framework": caught,
        "defects_escaped": escaped,
        "defect_detection_recall_pct": defect_detection_rate,
        "unvalidated_reporting_error_rate_pct": unvalidated_error_rate,
        "post_validation_reporting_error_rate_pct": post_validation_error_rate,
        "reporting_error_reduction_pct": error_reduction_pct,
        "breakdown": {
            "duplicates_caught": result["duplicates_caught"],
            "fuzzy_duplicates_caught": result["fuzzy_duplicates_caught"],
            "metadata_errors_caught": result["metadata_errors_caught"],
            "anomalies_caught": result["anomalies_caught"],
        },
    }

    out_dir = Path("data/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "latest_benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    md_lines = [
        "# Reproducible Data Quality Benchmark Report",
        "",
        f"- **Batch ID:** `{batch_id}`",
        f"- **Total Multi-Source Records Ingested:** {report['total_records_ingested']}",
        f"- **Injected Ground-Truth Defects:** {injected}",
        f"- **Defects Detected & Quarantined:** {caught} (**{defect_detection_rate}% recall**)",
        f"- **Baseline Reporting Error Rate:** {unvalidated_error_rate}%",
        f"- **Post-Validation Reporting Error Rate:** {post_validation_error_rate}%",
        f"- **Reporting Error Reduction:** **{error_reduction_pct}%**",
    ]
    (out_dir / "latest_benchmark.md").write_text("\n".join(md_lines), encoding="utf-8")
    return report


if __name__ == "__main__":
    metrics = run_benchmark()
    print(json.dumps(metrics, indent=2))
