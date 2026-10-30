BEGIN;

ALTER TABLE subscription_orders
    ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS subscription_orders_open_checkout_idx
    ON subscription_orders (user_id, created_at DESC)
    WHERE status IN ('created', 'pending') AND superseded_at IS NULL;

COMMIT;
