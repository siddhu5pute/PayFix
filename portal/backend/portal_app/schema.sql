-- Portal database schema (idempotent). Applied on startup under an advisory lock.

CREATE TABLE IF NOT EXISTS allowed_transitions (
    from_status TEXT NOT NULL,
    to_status   TEXT NOT NULL,
    PRIMARY KEY (from_status, to_status)
);

CREATE TABLE IF NOT EXISTS payments (
    txn_id              UUID PRIMARY KEY,
    razorpay_order_id   TEXT UNIQUE,
    razorpay_payment_id TEXT,
    payer_name          TEXT NOT NULL,
    payer_email         TEXT NOT NULL,
    purpose             TEXT NOT NULL,
    amount_paise        BIGINT NOT NULL CHECK (amount_paise > 0),
    currency            CHAR(3) NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
    status              TEXT NOT NULL CHECK (status IN ('created','pending','paid','failed','unknown','refunded')),
    status_note         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS payments_status_created_idx ON payments (status, created_at);

-- Every status change attempt, accepted or rejected
CREATE TABLE IF NOT EXISTS status_history (
    id          BIGSERIAL PRIMARY KEY,
    txn_id      UUID NOT NULL,
    from_status TEXT,
    to_status   TEXT NOT NULL,
    source      TEXT NOT NULL,
    accepted    BOOLEAN NOT NULL,
    reason      TEXT,
    details     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS status_history_txn_idx ON status_history (txn_id, id);

CREATE TABLE IF NOT EXISTS webhook_events (
    id          BIGSERIAL PRIMARY KEY,
    event_id    TEXT NOT NULL UNIQUE,
    event_type  TEXT NOT NULL,
    payload     JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed   BOOLEAN NOT NULL DEFAULT false,
    outcome     TEXT
);

CREATE TABLE IF NOT EXISTS rejected_webhooks (
    id          BIGSERIAL PRIMARY KEY,
    reason      TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- DB-level state machine: the code checks first, this trigger is the backstop.
CREATE OR REPLACE FUNCTION enforce_payment_transition() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'created' THEN
            RAISE EXCEPTION 'payments must be inserted as created, got %', NEW.status
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        IF NOT EXISTS (SELECT 1 FROM allowed_transitions
                       WHERE from_status = OLD.status AND to_status = NEW.status) THEN
            RAISE EXCEPTION 'invalid payment transition % -> %', OLD.status, NEW.status
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS payments_state_machine ON payments;
CREATE TRIGGER payments_state_machine
    BEFORE INSERT OR UPDATE ON payments
    FOR EACH ROW EXECUTE FUNCTION enforce_payment_transition();
