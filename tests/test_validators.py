import pytest
from src.validators.metadata import validate_record_metadata
from src.ingest import generate_multi_source_batch, load_batch_to_postgres
from src.pipeline import run_validation_pipeline
from src.db import get_conn


def test_metadata_validator_accepts_valid_record():
    record = {
        "full_name": "Elena Novak",
        "email": "elena.novak@example.org",
        "country_code": "AT",
        "consent_flag": "true",
        "birth_date": "1998-04-15",
    }
    assert validate_record_metadata(record) == []


@pytest.mark.parametrize(
    "bad_override,expected_fragment",
    [
        ({"full_name": "N/A"}, "full_name"),
        ({"email": "not-an-email"}, "email"),
        ({"country_code": "TBD"}, "country_code"),
        ({"consent_flag": "false"}, "consent_flag"),
        ({"birth_date": "2035-01-01"}, "future"),
    ],
)
def test_metadata_validator_catches_defects(bad_override, expected_fragment):
    base = {
        "full_name": "Lukas Weber",
        "email": "lukas.weber@example.org",
        "country_code": "DE",
        "consent_flag": "true",
        "birth_date": "1994-09-20",
    }
    base.update(bad_override)
    errors = validate_record_metadata(base)
    assert any(expected_fragment in err for err in errors)


def test_end_to_end_pipeline_integration():
    test_batch = "pytest_integration_batch"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM dq_validation_runs WHERE batch_id = %s", (test_batch,))
            cur.execute("DELETE FROM dim_registrations_clean WHERE batch_id = %s", (test_batch,))
            cur.execute("DELETE FROM raw_registrations WHERE batch_id = %s", (test_batch,))

    records, truth = generate_multi_source_batch(
        batch_id=test_batch, n_clean=120, seed=99, save_raw_files=False
    )
    load_batch_to_postgres(records)
    summary = run_validation_pipeline(batch_id=test_batch)

    assert summary["total_ingested"] == truth["total_generated"]
    assert summary["total_quarantined"] >= truth["total_injected_defects"]
    assert summary["validated_accuracy_pct"] >= 95.0