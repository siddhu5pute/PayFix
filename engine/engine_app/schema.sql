-- Reconciliation engine database (separate from the portal's database).

CREATE TABLE IF NOT EXISTS recon_runs (
    id          BIGSERIAL PRIMARY KEY,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    dry_run     BOOLEAN NOT NULL,
    collected   INT NOT NULL DEFAULT 0,
    mismatches  INT NOT NULL DEFAULT 0,
    resolved    INT NOT NULL DEFAULT 0,
    manual      INT NOT NULL DEFAULT 0,
    errors      INT NOT NULL DEFAULT 0,
    trigger     TEXT NOT NULL DEFAULT 'loop'
);

CREATE TABLE IF NOT EXISTS mismatches (
    id             BIGSERIAL PRIMARY KEY,
    txn_id         UUID NOT NULL,
    razorpay_order_id TEXT,
    amount_paise   BIGINT,
    portal_status  TEXT NOT NULL,
    gateway_status TEXT NOT NULL,
    mismatch_type  TEXT NOT NULL,
    detected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved       BOOLEAN NOT NULL DEFAULT false,
    resolution     TEXT,
    resolved_at    TIMESTAMPTZ,
    run_id         BIGINT REFERENCES recon_runs(id)
);
-- At most one OPEN mismatch of a given type per transaction
CREATE UNIQUE INDEX IF NOT EXISTS mismatches_open_uniq ON mismatches (txn_id, mismatch_type) WHERE NOT resolved;

-- Exactly-once guard: one row per (txn_id, action). INSERT ... ON CONFLICT DO NOTHING claims it.
CREATE TABLE IF NOT EXISTS resolutions (
    id          BIGSERIAL PRIMARY KEY,
    txn_id      UUID NOT NULL,
    action      TEXT NOT NULL,
    state       TEXT NOT NULL DEFAULT 'claimed' CHECK (state IN ('claimed','done','failed')),
    worker      TEXT,
    result      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    CONSTRAINT resolutions_once UNIQUE (txn_id, action)
);

CREATE TABLE IF NOT EXISTS manual_review (
    id          BIGSERIAL PRIMARY KEY,
    txn_id      UUID NOT NULL,
    reason      TEXT NOT NULL,
    portal_status  TEXT,
    gateway_status TEXT,
    details     JSONB NOT NULL DEFAULT '{}'::jsonb,
    status      TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS manual_review_open_uniq ON manual_review (txn_id) WHERE status = 'open';

-- Append-only audit trail
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    txn_id      UUID,
    run_id      BIGINT,
    step        TEXT NOT NULL,          -- COLLECT | DETECT | VERIFY | DECIDE | ACT | SKIP | ERROR | MANUAL_REVIEW | REFUND
    action      TEXT NOT NULL,
    from_status TEXT,
    to_status   TEXT,
    reason      TEXT,
    details     JSONB NOT NULL DEFAULT '{}'::jsonb,
    dry_run     BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS audit_log_txn_idx ON audit_log (txn_id, id);

CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % is not allowed', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log;
CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log;
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only();
