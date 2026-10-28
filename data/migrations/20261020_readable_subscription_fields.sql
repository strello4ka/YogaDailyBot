-- Rename subscription fields for a database used as the product admin view.
-- Apply only after explicitly selecting and checking the target database.
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'subscription_accounts'
          AND column_name = 'paid_starts_at'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'subscription_accounts'
          AND column_name = 'subscription_starts'
    ) THEN
        ALTER TABLE subscription_accounts RENAME COLUMN paid_starts_at TO subscription_starts;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'subscription_accounts'
          AND column_name = 'paid_ends_at'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'subscription_accounts'
          AND column_name = 'subscription_ends'
    ) THEN
        ALTER TABLE subscription_accounts RENAME COLUMN paid_ends_at TO subscription_ends;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'subscription_accounts'
          AND column_name = 'access_state'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'subscription_accounts'
          AND column_name = 'subscription_state'
    ) THEN
        ALTER TABLE subscription_accounts RENAME COLUMN access_state TO subscription_state;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'subscription_orders'
          AND column_name = 'base_amount_kopecks'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'subscription_orders'
          AND column_name = 'base_price'
    ) THEN
        ALTER TABLE subscription_orders RENAME COLUMN base_amount_kopecks TO base_price;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'subscription_orders'
          AND column_name = 'amount_kopecks'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'subscription_orders'
          AND column_name = 'final_price'
    ) THEN
        ALTER TABLE subscription_orders RENAME COLUMN amount_kopecks TO final_price;
    END IF;
END $$;

COMMIT;
