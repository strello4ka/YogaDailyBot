BEGIN;

ALTER TABLE subscription_orders DROP CONSTRAINT subscription_orders_status_check;
ALTER TABLE subscription_orders ADD CONSTRAINT subscription_orders_status_check
    CHECK (status IN ('created', 'pending', 'succeeded', 'canceled', 'expired'));

COMMIT;
