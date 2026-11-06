-- First production subscription schema. Prepared only; never run automatically.
-- It creates storage but does not enroll users, grant access or send messages.
BEGIN;

DO $$
DECLARE
    target_tables TEXT[] := ARRAY[
        'subscription_accounts',
        'subscription_orders',
        'subscription_notifications',
        'subscription_daily_practices',
        'old_user_feedback'
    ];
BEGIN
    IF current_database() = 'yogadaily_test' THEN
        RAISE EXCEPTION 'Production migration cannot run on yogadaily_test';
    END IF;
    IF EXISTS (
        SELECT 1 FROM unnest(target_tables) AS target(name)
        WHERE to_regclass('public.' || target.name) IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'A target subscription table already exists; inspect schema before continuing';
    END IF;
    IF to_regclass('public.users') IS NULL THEN
        RAISE EXCEPTION 'Required users table is missing';
    END IF;
END $$;

CREATE TABLE subscription_accounts (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    trial_started_at TIMESTAMPTZ,
    trial_ends_at TIMESTAMPTZ,
    subscription_starts TIMESTAMPTZ,
    subscription_ends TIMESTAMPTZ,
    email TEXT,
    subscription_state TEXT NOT NULL DEFAULT 'free'
        CHECK (subscription_state IN ('free','trial','trial_paid','gift','gift_paid','paid')),
    is_old_user BOOLEAN NOT NULL DEFAULT FALSE,
    gift_starts TIMESTAMPTZ,
    gift_ends TIMESTAMPTZ,
    offer_ends TIMESTAMPTZ,
    special_offer_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((trial_started_at IS NULL AND trial_ends_at IS NULL) OR
           (trial_started_at IS NOT NULL AND trial_ends_at IS NOT NULL
            AND trial_ends_at > trial_started_at)),
    CHECK ((subscription_starts IS NULL AND subscription_ends IS NULL) OR
           (subscription_starts IS NOT NULL AND subscription_ends IS NOT NULL
            AND subscription_ends > subscription_starts)),
    CHECK ((is_old_user IS FALSE AND gift_starts IS NULL AND gift_ends IS NULL
            AND offer_ends IS NULL AND special_offer_used_at IS NULL) OR
           (is_old_user IS TRUE AND gift_starts IS NOT NULL AND gift_ends IS NOT NULL
            AND offer_ends IS NOT NULL AND gift_ends > gift_starts AND offer_ends > gift_ends))
);

CREATE TABLE subscription_orders (
    order_id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES subscription_accounts(user_id) ON DELETE CASCADE,
    tariff_code TEXT NOT NULL,
    duration_days INTEGER NOT NULL CHECK (duration_days > 0),
    base_price INTEGER NOT NULL CHECK (base_price > 0),
    final_price INTEGER NOT NULL CHECK (final_price > 0),
    currency TEXT NOT NULL DEFAULT 'RUB' CHECK (currency = 'RUB'),
    email TEXT NOT NULL,
    payment_scope TEXT NOT NULL CHECK (payment_scope ~ '^(test|live):[0-9]+$'),
    provider_payment_id TEXT UNIQUE,
    status TEXT NOT NULL DEFAULT 'created'
        CHECK (status IN ('created', 'pending', 'succeeded', 'canceled')),
    special_offer_applied BOOLEAN NOT NULL DEFAULT FALSE,
    offer_ends_at_order TIMESTAMPTZ,
    granted_at TIMESTAMPTZ,
    period_starts_at TIMESTAMPTZ,
    period_ends_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((special_offer_applied IS FALSE AND final_price = base_price) OR
           (special_offer_applied IS TRUE AND final_price < base_price
            AND offer_ends_at_order IS NOT NULL)),
    CHECK (granted_at IS NULL OR
           (status = 'succeeded' AND period_starts_at IS NOT NULL
            AND period_ends_at IS NOT NULL AND period_ends_at > period_starts_at))
);
CREATE INDEX subscription_orders_user_id_idx ON subscription_orders(user_id);
CREATE INDEX subscription_orders_open_checkout_idx
    ON subscription_orders (user_id, payment_scope, created_at DESC)
    WHERE status IN ('created', 'pending');

CREATE TABLE subscription_notifications (
    user_id BIGINT NOT NULL REFERENCES subscription_accounts(user_id) ON DELETE CASCADE,
    event_key TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, event_key)
);

CREATE TABLE subscription_daily_practices (
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    moscow_date DATE NOT NULL,
    practice_catalog TEXT NOT NULL,
    practice_id BIGINT NOT NULL,
    PRIMARY KEY (user_id, moscow_date)
);

CREATE TABLE old_user_feedback (
    feedback_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    username TEXT,
    feedback_text TEXT NOT NULL CHECK (length(btrim(feedback_text)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX old_user_feedback_created_at_idx ON old_user_feedback(created_at DESC);
CREATE INDEX old_user_feedback_user_id_idx ON old_user_feedback(user_id);

COMMIT;
