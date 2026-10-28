-- Prepared schema for the one-off old-users transition.
-- Applying it does not enroll users, grant access, send messages or enable prices.
BEGIN;

ALTER TABLE subscription_accounts
    ADD COLUMN IF NOT EXISTS is_old_user BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gift_starts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS gift_ends TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS offer_ends TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS special_offer_used_at TIMESTAMPTZ;

ALTER TABLE subscription_accounts
    DROP CONSTRAINT IF EXISTS subscription_accounts_access_state_check;
ALTER TABLE subscription_accounts
    DROP CONSTRAINT IF EXISTS subscription_accounts_state_check;
ALTER TABLE subscription_accounts
    ADD CONSTRAINT subscription_accounts_state_check
    CHECK (subscription_state IN ('free','trial','trial_paid','gift','gift_paid','paid'));

ALTER TABLE subscription_accounts
    DROP CONSTRAINT IF EXISTS subscription_accounts_old_user_dates_check;
ALTER TABLE subscription_accounts
    ADD CONSTRAINT subscription_accounts_old_user_dates_check
    CHECK ((is_old_user IS FALSE AND gift_starts IS NULL AND gift_ends IS NULL
            AND offer_ends IS NULL AND special_offer_used_at IS NULL) OR
           (is_old_user IS TRUE AND gift_starts IS NOT NULL AND gift_ends IS NOT NULL
            AND offer_ends IS NOT NULL AND gift_ends > gift_starts AND offer_ends > gift_ends));

ALTER TABLE subscription_orders
    ADD COLUMN IF NOT EXISTS special_offer_applied BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS offer_ends_at_order TIMESTAMPTZ;

ALTER TABLE subscription_orders
    DROP CONSTRAINT IF EXISTS subscription_orders_old_user_price_check;
ALTER TABLE subscription_orders
    ADD CONSTRAINT subscription_orders_old_user_price_check
    CHECK ((special_offer_applied IS FALSE AND final_price = base_price) OR
           (special_offer_applied IS TRUE AND final_price < base_price
            AND offer_ends_at_order IS NOT NULL));

COMMIT;
