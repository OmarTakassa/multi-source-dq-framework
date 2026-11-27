-- 1. Raw multi-source landing table
CREATE TABLE IF NOT EXISTS raw_registrations (
    raw_id              BIGSERIAL PRIMARY KEY,
    batch_id            VARCHAR(64) NOT NULL,
    source_system       VARCHAR(32) NOT NULL, -- 'web_portal', 'partner_api', 'legacy_csv'
    external_reg_id     VARCHAR(128),
    full_name           TEXT,
    email               TEXT,
    phone               TEXT,
    birth_date          TEXT,
    country_code        TEXT,
    consent_flag        TEXT,
    submitted_at        TEXT,
    approved_at         TEXT,
    status              TEXT,
    raw_payload         JSONB NOT NULL,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_registrations_batch ON raw_registrations(batch_id);

-- 2. Normalized staging table
CREATE TABLE IF NOT EXISTS stg_registrations (
    stg_id              BIGSERIAL PRIMARY KEY,
    raw_id              BIGINT NOT NULL REFERENCES raw_registrations(raw_id) ON DELETE CASCADE,
    batch_id            VARCHAR(64) NOT NULL,
    source_system       VARCHAR(32) NOT NULL,
    external_reg_id     VARCHAR(128),
    full_name_norm      TEXT,
    email_norm          TEXT,
    phone_norm          TEXT,
    birth_date_parsed   DATE,
    country_code_norm   VARCHAR(8),
    consent_valid       BOOLEAN,
    submitted_at_ts     TIMESTAMPTZ,
    approved_at_ts      TIMESTAMPTZ,
    status_norm         VARCHAR(32),
    identity_hash       VARCHAR(64),
    is_valid            BOOLEAN DEFAULT TRUE,
    processed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stg_identity_hash ON stg_registrations(identity_hash);
CREATE INDEX IF NOT EXISTS idx_stg_batch_id ON stg_registrations(batch_id);

-- 3. Quarantine sink for failed records
CREATE TABLE IF NOT EXISTS quarantine_records (
    quarantine_id       BIGSERIAL PRIMARY KEY,
    raw_id              BIGINT NOT NULL REFERENCES raw_registrations(raw_id) ON DELETE CASCADE,
    batch_id            VARCHAR(64) NOT NULL,
    source_system       VARCHAR(32) NOT NULL,
    rule_id             VARCHAR(64) NOT NULL,
    severity            VARCHAR(16) NOT NULL, -- 'CRITICAL', 'WARNING'
    failure_reason      TEXT NOT NULL,
    raw_payload         JSONB NOT NULL,
    quarantined_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quarantine_batch ON quarantine_records(batch_id);

-- 4. Validated reporting table
CREATE TABLE IF NOT EXISTS dim_registrations_clean (
    clean_id            BIGSERIAL PRIMARY KEY,
    stg_id              BIGINT UNIQUE NOT NULL REFERENCES stg_registrations(stg_id),
    batch_id            VARCHAR(64) NOT NULL,
    source_system       VARCHAR(32) NOT NULL,
    external_reg_id     VARCHAR(128),
    full_name           TEXT NOT NULL,
    email               TEXT NOT NULL,
    phone               TEXT,
    birth_date          DATE NOT NULL,
    country_code        VARCHAR(8) NOT NULL,
    consent_flag        BOOLEAN NOT NULL,
    submitted_at        TIMESTAMPTZ NOT NULL,
    approved_at         TIMESTAMPTZ,
    status              VARCHAR(32) NOT NULL,
    identity_hash       VARCHAR(64) UNIQUE NOT NULL,
    validated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Observability & audit ledger
CREATE TABLE IF NOT EXISTS dq_validation_runs (
    run_id                  BIGSERIAL PRIMARY KEY,
    batch_id                VARCHAR(64) UNIQUE NOT NULL,
    started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at            TIMESTAMPTZ,
    total_ingested          INT NOT NULL DEFAULT 0,
    total_passed            INT NOT NULL DEFAULT 0,
    total_quarantined       INT NOT NULL DEFAULT 0,
    duplicate_count         INT NOT NULL DEFAULT 0,
    metadata_error_count    INT NOT NULL DEFAULT 0,
    anomaly_count           INT NOT NULL DEFAULT 0,
    baseline_accuracy_pct   NUMERIC(6,2),
    validated_accuracy_pct  NUMERIC(6,2),
    ai_triage_summary       TEXT
);
