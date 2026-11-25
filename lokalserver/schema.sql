BEGIN;

CREATE TABLE IF NOT EXISTS medirover_orders (
    request_id uuid PRIMARY KEY,
    station smallint NOT NULL CHECK (station IN (1, 2)),
    status text NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE medirover_orders
    DROP CONSTRAINT IF EXISTS medirover_orders_status_check,
    ADD CONSTRAINT medirover_orders_status_check
        CHECK (status IN ('pending', 'running', 'completed'));

CREATE UNIQUE INDEX IF NOT EXISTS medirover_one_running_order
    ON medirover_orders (status) WHERE status = 'running';

COMMIT;
