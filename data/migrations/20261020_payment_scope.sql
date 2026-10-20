-- Apply only to local yogadaily_test, with bot and payment backend stopped.
-- Historical orders in this database were created in test shop 1497096.
BEGIN;
DO $$ BEGIN
    IF current_database() <> 'yogadaily_test' THEN
        RAISE EXCEPTION 'This migration is restricted to yogadaily_test';
    END IF;
END $$;
ALTER TABLE subscription_orders ADD COLUMN IF NOT EXISTS
    payment_scope TEXT NOT NULL DEFAULT 'test:1497096';
COMMIT;
