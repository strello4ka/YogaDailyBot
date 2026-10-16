-- Prepared migration only. Apply to an explicitly selected test DB first.
-- It does not enroll existing users or change their access.
BEGIN;

CREATE TABLE IF NOT EXISTS subscription_accounts (
    user_id BIGINT PRIMARY KEY,
    trial_started_at TIMESTAMPTZ,
    trial_ends_at TIMESTAMPTZ,
    paid_starts_at TIMESTAMPTZ,
    paid_ends_at TIMESTAMPTZ,
    email TEXT,
    access_state TEXT NOT NULL DEFAULT 'free'
        CHECK (access_state IN ('free', 'trial', 'trial_paid', 'paid')),
    schedule_restore_required BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((trial_started_at IS NULL AND trial_ends_at IS NULL) OR
           (trial_started_at IS NOT NULL AND trial_ends_at IS NOT NULL
            AND trial_ends_at > trial_started_at)),
    CHECK ((paid_starts_at IS NULL AND paid_ends_at IS NULL) OR
           (paid_starts_at IS NOT NULL AND paid_ends_at IS NOT NULL
            AND paid_ends_at > paid_starts_at))
);

CREATE TABLE IF NOT EXISTS subscription_orders (
    order_id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES subscription_accounts(user_id),
    tariff_code TEXT NOT NULL,
    duration_days INTEGER NOT NULL CHECK (duration_days > 0),
    base_amount_kopecks INTEGER NOT NULL CHECK (base_amount_kopecks > 0),
    amount_kopecks INTEGER NOT NULL CHECK (amount_kopecks > 0),
    currency TEXT NOT NULL DEFAULT 'RUB' CHECK (currency = 'RUB'),
    email TEXT NOT NULL,
    provider_payment_id TEXT UNIQUE,
    status TEXT NOT NULL DEFAULT 'created'
        CHECK (status IN ('created', 'pending', 'succeeded', 'canceled')),
    granted_at TIMESTAMPTZ,
    period_starts_at TIMESTAMPTZ,
    period_ends_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (granted_at IS NULL OR
           (status = 'succeeded' AND period_starts_at IS NOT NULL
            AND period_ends_at IS NOT NULL AND period_ends_at > period_starts_at))
);
CREATE INDEX IF NOT EXISTS subscription_orders_user_id_idx
    ON subscription_orders(user_id);

CREATE TABLE IF NOT EXISTS subscription_notifications (
    user_id BIGINT NOT NULL REFERENCES subscription_accounts(user_id),
    event_key TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, event_key)
);

CREATE TABLE IF NOT EXISTS subscription_daily_practices (
    user_id BIGINT NOT NULL,
    moscow_date DATE NOT NULL,
    practice_catalog TEXT NOT NULL,
    practice_id BIGINT NOT NULL,
    PRIMARY KEY (user_id, moscow_date)
);

COMMIT;
