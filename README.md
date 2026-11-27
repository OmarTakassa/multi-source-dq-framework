# Automated Multi-Source Data Validation & Process Quality Framework

End-to-end data quality and observability framework built with **Python**, **SQL**, **PostgreSQL**, and **AI incident triage** to detect duplicate records, missing metadata, and workflow anomalies across multi-source registration pipelines (\web_portal\, \partner_api\, \legacy_csv\).

## Key Capabilities & Verified Benchmark
- **Multi-Layer PostgreSQL Architecture:** Separates raw landing (aw_registrations\), normalized staging (\stg_registrations\), exception quarantine (\quarantine_records\), clean reporting (\dim_registrations_clean\), and run observability (\dq_validation_runs\).
- **Hybrid SQL + Python Validation Engine:**
  - \META_001\: Enforces required metadata completeness, regex email formats, ISO country codes, and explicit consent flags.
  - \DUP_001\ & \DUP_FUZZY_002\: Combines deterministic MD5 identity hashing with blocked \RapidFuzz\ token-sort similarity matching to catch exact and near-duplicate records across sources.
  - \ANOM_001\ & MAD Volume Checks: Flags inverted workflow timestamps (\pproved_at < submitted_at\), temporal anomalies, and batch volume shifts using Median Absolute Deviation (MAD).
- **AI-Assisted Incident Triage:** Generates root-cause summaries from deterministic audit logs (\src/ai_triage.py\), falling back cleanly to rule-based digests when offline.
- **Verified Benchmark Impact:** Reduces baseline unvalidated reporting error rate from **7.22% to 0.00%** (**>95% error reduction / 100% defect recall** on reproducible benchmark runs in \data/benchmarks/latest_benchmark.json\).

## Quickstart
1. Create a PostgreSQL database named egistration_dq\ and execute \sql/01_schema.sql\.
2. Copy \.env.example\ to \.env\ and configure your PostgreSQL credentials.
3. Install dependencies and run the benchmark and test suite:
   \\ash
   python -m venv .venv
   # Windows PowerShell: .\\.venv\\Scripts\\Activate.ps1
   pip install -r requirements.txt
   python benchmark.py
   pytest
   ```
