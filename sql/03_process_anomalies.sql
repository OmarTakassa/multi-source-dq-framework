-- Rule ANOM_001: Temporal & workflow state-transition anomalies
WITH workflow_anomalies AS (
    SELECT
        s.stg_id,
        s.raw_id,
        s.batch_id,
        s.source_system,
        r.raw_payload,
        CASE
            WHEN s.submitted_at_ts IS NULL THEN 'Missing submitted_at timestamp'
            WHEN s.approved_at_ts IS NOT NULL AND s.approved_at_ts < s.submitted_at_ts
                THEN 'State transition violation: approved_at precedes submitted_at'
            WHEN s.birth_date_parsed > CURRENT_DATE
                THEN 'Temporal anomaly: birth_date is in the future'
            WHEN s.birth_date_parsed > (s.submitted_at_ts::DATE - INTERVAL '16 years')
                THEN 'Age policy anomaly: registrant under 16 years old at submission'
            WHEN s.status_norm = 'approved' AND s.approved_at_ts IS NULL
                THEN 'State mismatch: status is approved without approved_at timestamp'
        END AS reason
    FROM stg_registrations s
    JOIN raw_registrations r ON r.raw_id = s.raw_id
    WHERE s.batch_id = %(batch_id)s
      AND s.is_valid = TRUE
)
INSERT INTO quarantine_records (raw_id, batch_id, source_system, rule_id, severity, failure_reason, raw_payload)
SELECT raw_id, batch_id, source_system, 'ANOM_001', 'CRITICAL', reason, raw_payload
FROM workflow_anomalies
WHERE reason IS NOT NULL;

UPDATE stg_registrations s
SET is_valid = FALSE
FROM quarantine_records q
WHERE q.raw_id = s.raw_id
  AND s.batch_id = %(batch_id)s
  AND q.rule_id = 'ANOM_001';
