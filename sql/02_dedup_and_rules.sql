-- Parameterized batch execution helper: replaces :batch_id via Python psycopg
-- 1. Promote & normalize raw records into stg_registrations
INSERT INTO stg_registrations (
    raw_id, batch_id, source_system, external_reg_id,
    full_name_norm, email_norm, phone_norm,
    birth_date_parsed, country_code_norm, consent_valid,
    submitted_at_ts, approved_at_ts, status_norm, identity_hash, is_valid
)
SELECT
    r.raw_id,
    r.batch_id,
    r.source_system,
    TRIM(r.external_reg_id),
    LOWER(REGEXP_REPLACE(TRIM(COALESCE(r.full_name, '')), '\s+', ' ', 'g')),
    LOWER(TRIM(COALESCE(r.email, ''))),
    REGEXP_REPLACE(COALESCE(r.phone, ''), '[^0-9+]', '', 'g'),
    CASE
        WHEN r.birth_date ~ '^\d{4}-\d{2}-\d{2}$' THEN r.birth_date::DATE
        ELSE NULL
    END,
    UPPER(TRIM(COALESCE(r.country_code, ''))),
    CASE
        WHEN LOWER(TRIM(COALESCE(r.consent_flag, ''))) IN ('true', '1', 'yes', 'y') THEN TRUE
        ELSE FALSE
    END,
    NULLIF(TRIM(r.submitted_at), '')::TIMESTAMPTZ,
    NULLIF(TRIM(r.approved_at), '')::TIMESTAMPTZ,
    LOWER(TRIM(COALESCE(r.status, 'pending'))),
    MD5(
        LOWER(TRIM(COALESCE(r.email, ''))) || '|' ||
        COALESCE(r.birth_date, '')
    ),
    TRUE
FROM raw_registrations r
WHERE r.batch_id = %(batch_id)s
  AND NOT EXISTS (
      SELECT 1 FROM stg_registrations s WHERE s.raw_id = r.raw_id
  );

-- 2. Rule META_001: Missing or placeholder required metadata
WITH bad_meta AS (
    SELECT
        s.stg_id, s.raw_id, s.batch_id, s.source_system, r.raw_payload,
        CASE
            WHEN s.full_name_norm IN ('', 'n/a', 'na', 'tbd', 'null', 'none', '-') THEN 'Missing or placeholder full_name'
            WHEN s.email_norm = '' OR s.email_norm !~ '^[a-z0-9._%%+-]+@[a-z0-9.-]+\.[a-z]{2,}$' THEN 'Missing or malformed email'
            WHEN s.country_code_norm IN ('', 'N/A', 'TBD', 'XX') OR LENGTH(s.country_code_norm) <> 2 THEN 'Invalid or placeholder country_code'
            WHEN s.birth_date_parsed IS NULL THEN 'Missing or unparseable birth_date'
            WHEN s.consent_valid IS NOT TRUE THEN 'Explicit user consent_flag missing or false'
        END AS reason
    FROM stg_registrations s
    JOIN raw_registrations r ON r.raw_id = s.raw_id
    WHERE s.batch_id = %(batch_id)s
      AND s.is_valid = TRUE
)
INSERT INTO quarantine_records (raw_id, batch_id, source_system, rule_id, severity, failure_reason, raw_payload)
SELECT raw_id, batch_id, source_system, 'META_001', 'CRITICAL', reason, raw_payload
FROM bad_meta
WHERE reason IS NOT NULL;

UPDATE stg_registrations s
SET is_valid = FALSE
FROM quarantine_records q
WHERE q.raw_id = s.raw_id
  AND s.batch_id = %(batch_id)s
  AND q.rule_id = 'META_001';

-- 3. Rule DUP_001: Exact cross-source duplicate detection (within batch or against clean warehouse)
WITH ranked_dups AS (
    SELECT
        s.stg_id,
        s.raw_id,
        s.batch_id,
        s.source_system,
        r.raw_payload,
        ROW_NUMBER() OVER (
            PARTITION BY s.identity_hash
            ORDER BY
                CASE s.source_system
                    WHEN 'web_portal' THEN 1
                    WHEN 'partner_api' THEN 2
                    ELSE 3
                END ASC,
                s.stg_id ASC
        ) AS rn,
        EXISTS (
            SELECT 1 FROM dim_registrations_clean d WHERE d.identity_hash = s.identity_hash
        ) AS already_in_clean
    FROM stg_registrations s
    JOIN raw_registrations r ON r.raw_id = s.raw_id
    WHERE s.batch_id = %(batch_id)s
      AND s.is_valid = TRUE
)
INSERT INTO quarantine_records (raw_id, batch_id, source_system, rule_id, severity, failure_reason, raw_payload)
SELECT
    raw_id,
    batch_id,
    source_system,
    'DUP_001',
    'CRITICAL',
    CASE
        WHEN already_in_clean THEN 'Duplicate identity_hash already exists in dim_registrations_clean'
        ELSE 'Exact duplicate identity_hash within ingestion batch'
    END,
    raw_payload
FROM ranked_dups
WHERE rn > 1 OR already_in_clean = TRUE;

UPDATE stg_registrations s
SET is_valid = FALSE
FROM quarantine_records q
WHERE q.raw_id = s.raw_id
  AND s.batch_id = %(batch_id)s
  AND q.rule_id = 'DUP_001';

