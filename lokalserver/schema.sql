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

CREATE TABLE IF NOT EXISTS medirover_temperatures (
    id bigserial PRIMARY KEY,
    temperature_c numeric(5,2) NOT NULL CHECK (temperature_c BETWEEN -100 AND 150),
    measured_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE medirover_temperatures
    ADD COLUMN IF NOT EXISTS humidity_percent numeric(5,2)
        CHECK (humidity_percent BETWEEN 0 AND 100);
CREATE INDEX IF NOT EXISTS medirover_temperature_latest
    ON medirover_temperatures (measured_at DESC, id DESC);

COMMIT;
